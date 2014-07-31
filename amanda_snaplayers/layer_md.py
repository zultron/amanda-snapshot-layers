# MD RAID device

import re, os.path
from stack import Stack
from layers import Layer


class MD_component_device(Layer):
    '''
    A Linux md RAID1 device (other raid levels not supported)

    This class detects and assembles/disassembles RAID1 mirrors in
    degraded mode (half device) for backups
    '''

    name = 'md'
    mdadm = '/sbin/mdadm'
    raid1_re = re.compile(r' level=raid1 ')
    uuid_re = re.compile(r'UUID=([0-9a-f:]+)')
    md_dev_re = re.compile(r'^md([0-9]+)$')

    def __init__(self,arg_str,params,parent_layer):
        super(MD_component_device,self).__init__(arg_str,params,parent_layer)
        self.md_dev = None
        self.dev_uuid = None
        self.dev_db = None
        self.found_md_raid1_device = None

    def print_info(self):
        self.infomsg("Initialized md component device object parameters:")
        self.infomsg("    component device = %s" % self.parent_device)

    def md_device_exists(self,device=None):
        if device is None:
            device = self.md_device
        return os.path.exists(device)

    @property
    def device_exists(self):
        return os.path.exists(self.parent_device)

    def _extract_uuid(self,line):
        s = self.uuid_re.search(line)
        if s is None:
            return None
        return s.groups()[0]

    def _other_md_device_running(self, md_device,
                                 return_all_results=False, fail_abort=False):
        cmd = [self.mdadm, '-D', md_device, '-b']
        (res,stdout,stderr) = self.run_cmd(
            cmd, sudo=True, t_f=True, fail_abort=fail_abort)
        if return_all_results:
            return (res,stdout,stderr)
        else:
            return res

    def in_running_md_device(self,recheck=False):

        # don't re-run check unless told to
        if self.md_dev is not None:
            if self.md_dev == -1:
                return None
            else:
                return self.md_dev

        # get md array UUID for matching
        my_uuid = self.get_uuid

        # reset dev_db
        self.dev_db = {}

        for devnum in [int(i[2:]) for i in os.listdir("/dev")
                       if self.md_dev_re.match(i)]:
            md_dev = '/dev/md%d' % devnum

            (res, stdout, stderr) = \
                  self._other_md_device_running(md_dev, return_all_results=True)
            if res is None:
                self.dev_db[md_dev] = -1
                self.debugmsg(
                    "     failed to check device %s; ignoring" % md_dev)
                continue
            if not res:
                self.dev_db[md_dev] = 0
                self.debugmsg(
                    "     Device %s not running; ignoring" % md_dev)
                continue

            uuid = self._extract_uuid(stdout)
            if uuid is None:
                self.dev_db[md_dev] = -1
                self.debugmsg("     Unable to determine UUID for device %s; "
                              "ignoring" % md_dev)
                continue
            if uuid == my_uuid:
                self.md_dev = md_dev
                self.dev_db[md_dev] = 1
                self.debugmsg("  Target device is member of "
                              "running md device %s" % self.md_dev)
                return self.md_dev
        
            self.debugmsg("     Device %s does not contain our component "
                          "device; ignoring" % md_dev)

        self.md_dev = -1
        return None


    @property
    def is_md_raid1_component_device(self):
        # don't check again
        if self.found_md_raid1_device is not None:
            return True

        cmd = [self.mdadm, '-Q', self.parent_device, '--examine', '-b']
        (res,stdout,stderr) = self.run_cmd(cmd)
        self.found_md_raid1_device = (res and
                                      self.raid1_re.search(stdout) is not None)

        return self.found_md_raid1_device

    @property
    def get_uuid(self):
        if self.dev_uuid is not None:
            return self.dev_uuid

        cmd = [self.mdadm, '-Q', '--examine', self.parent_device, '-b']
        (res,stdout,stderr) = self.run_cmd(cmd)
        self.dev_uuid = self._extract_uuid(stdout)
        if self.dev_uuid is None:
            self.error("unable to determine md device UUID for %s" %
                       self.parent_device)
        self.debugmsg("  Found snapshot array UUID = %s" % self.dev_uuid)
        return self.dev_uuid

    @property
    def md_device(self):
        # if part of a running md array, return that
        if self.in_running_md_device() is not None:
            return self.in_running_md_device()

        # otherwise, find an unused md device
        for i in xrange(10):
            candidate_dev = "/dev/md%d" % i
            if self.dev_db.get(candidate_dev,None) is not None:
                continue
            if not self.md_device_exists(candidate_dev):
                self.md_dev = candidate_dev
                self.debugmsg("  Selecting unused md device %s" %
                              candidate_dev)
                break
            cand_status = self._other_md_device_running(candidate_dev)
            if cand_status is None:
                self.debugmsg("    Ignoring uncheckable md device %s" %
                              candidate_dev)
            elif cand_status is True:
                self.debugmsg("    md device %s in use" % candidate_dev)
            else:
                self.md_dev = candidate_dev
                self.debugmsg("    Found unused md device %s" % candidate_dev)
                break
        if self.md_dev is None:
            self.error("Unable to find unused md device node; aborting")
        return self.md_dev

    @property
    def device(self):
        if self.is_setup:
            return self.md_device
        else:
            return None

    @property
    def md_device_running(self):
        return self._other_md_device_running(self.md_dev)

    @property
    def is_setup(self):
        return self.in_running_md_device(recheck=True) is not None

    def assemble_md_device(self):
        cmd = [self.mdadm, '-A', self.md_device, self.parent_device, '--run']
        (res,stdout,stderr) = self.run_cmd(cmd)

    def stop_md_device(self):
        cmd = [self.mdadm, '-S', self.md_device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        self.infomsg("  Ran 'mdadm -S' command")
        
    def safe_set_up(self):
        self.infomsg("Assembling md array")

        # sanity check:  snapshot device is an md array component
        if not self.is_md_raid1_component_device:
            self.error("Device %s is not an md RAID1 "
                       "component device; aborting" % self.parent_device)
        self.debugmsg("  Sanity check passed:  "
                      "device is an md RAID1 component device")

        # if snapshot device is part of a running md array, nothing to do
        if self.in_running_md_device():
            self.infomsg("Device is already part of running md array\n")
            return
        self.debugmsg("  Device not already part of any running md array")

        self.assemble_md_device()
        self.infomsg("  Ran 'mdadm -A %s' command" % self.md_device)

        # check device status
        if not self.md_device_exists:
            self.error("md device %s does not exist after assembly; aborting" %
                       self.md_device)
        self.debugmsg("  Sanity check passed:  md device exists")

        if not self.md_device_running:
            self.error("md device %s exists but not running after assembly; "
                       "aborting" % self.md_device)
        self.debugmsg("  Sanity check passed:  md device running")

        self.infomsg("Successfully started md array\n")



    def safe_teardown(self):
        self.infomsg("Stopping md array")

        # if component device is not running, there's nothing to do
        if not self.device_exists:
            self.infomsg("Component device does not exist; nothing to stop\n")
            return
        self.debugmsg("  Sanity check passed:  md component device exists")

        # if md array is not running, there's nothing to do
        if not self.in_running_md_device():
            self.infomsg("Device is not part of any running md array; "
                         "nothing to stop\n")
            return
        self.debugmsg("  Sanity check passed:  "
                      "device is component of running array")

        # FIXME: unimplemented
        # sanity check:  snapshot device is component of the array we just
        # unmounted
        
        #if not self.is_component_device_of(md_dev):
        #    self.error("Device is not a component device of the array; "
        #               "aborting")

        self.stop_md_device()

        # check device status
        if self.md_device_running:
            self.error("md device %s still running after stopping; "
                       "aborting" % self.md_device)
        self.debugmsg("  Sanity check passed:  md device not still running")

        #if self.md_device_exists():
        #    self.error("md device file %s still exists after stopping; "
        #               "aborting" % self.md_device)
        #self.debugmsg("  Sanity check passed:  md device no longer exists")

        self.infomsg("Stopped md array %s\n" % self.in_running_md_device())

        # reset attributes in case the object is reused
        self.md_dev = None
        self.dev_uuid = None
        self.dev_db = None

# Register this layer
Stack.register_layer(MD_component_device)
