# Mount a volume

import re, os.path, time

from stack import Stack,Mount
from layers import Layer
from params import Params


# Mount parameters
Params.add_option(
    "--no_auto_mount", "--no-auto-mount",
    help=("don't automatically try to automount the final device; "
          "mount must be specified explicitly"))


class MountPartition(Layer,Mount):
    name = 'part'
    mount_cmd = '/bin/mount'
    umount_cmd = '/bin/umount'

    def __init__(self,arg_str,params,parent_layer):

        super(MountPartition,self).__init__(arg_str,params,parent_layer)

        self.mount_db = None


    def print_info(self):
        self.infomsg("Initialized mount object parameters:")
        # Don't print parent_device; this invokes unwanted mdadm runs
        # if the underlying RAID1 layer isn't set up
        #self.infomsg("    device = %s" % self.parent_device)
        self.infomsg("    mount point = %s" % self.mount_point)
        self.infomsg("    base mount directory = %s" % self.mount_base)
        self.infomsg("    real base mount directory = %s" %
                     self.real_mount_base)

    @property
    def parent_device(self):
        if self.arg_str and self.arg_str != '0':
            # partitioned parent device
            return self.parent.device_partition(self.arg_str)
        else:
            return self.parent.device

    @property
    def mount_point(self):
        return self.params.device

    @property
    def mount_base(self):
        return self.params.mount_base

    @property
    def mount_re(self):
        if getattr(self,'mount_re_compiled',None) is None:
            self.mount_re_compiled =  re.compile(
                r'^([^ ]*) (%s/[^ ]*)' %
                os.path.realpath(self.real_mount_base))
        return self.mount_re_compiled

    @property
    def real_mount_base(self):
        return os.path.realpath(self.mount_base)

    def device_exists_wait(self,timeout):
        res = False
        for i in xrange(timeout+1):
            res = os.path.exists(self.parent_device)
            if res:
                break
            time.sleep(0.1)
        return res

    @property
    def device_exists(self):
        return os.path.exists(self.parent_device)

    @property
    def device(self):
        if self.is_setup:
            return self.mount_point
        else:
            return None

    @property
    def mount_point_exists(self):
        if not os.path.exists(self.mount_point):
            # try to create it
            cmd = ['mkdir', self.mount_point]
            (res,stderr,stdout) = self.run_cmd(cmd)
            if not res:
                error("Unable to create mount point '%s':\n%s" %
                      (self.mount_point, stderr))
            self.debugmsg("  Created mount point directory %s" %
                          self.mount_point)
        return True

    def remove_mount_point(self):
        if os.path.exists(self.mount_point):
            (res,stderr,stdout) = self.run_cmd(['rmdir', self.mount_point])
            if not res:
                error("Unable to remove mount point '%s':\n%s" %
                      (self.mount_point, stderr))
            self.debugmsg("  Removed mount point directory %s" %
                          self.mount_point)

    @property
    def mount_point_is_directory(self):
        return os.path.isdir(self.mount_point)

    @property
    def real_mount_point(self):
        return os.path.realpath(self.mount_point)

    def build_mount_db(self, rebuild=False):
        if not rebuild and self.mount_db is not None:
            return self.mount_db

        self.mount_db = { 'mount_dev' : {},
                          'mount_point' : {} }

        try:
            fd = open('/proc/mounts','r')
            for line in fd:
                m = self.mount_re.match(line)
                if m is None:
                    continue
                self.mount_db['mount_dev'][m.groups()[0]] = m.groups()[1]
                self.mount_db['mount_point'][m.groups()[1]] = m.groups()[0]
                self.debugmsg("    found mount '%s' -> '%s'" %
                              m.groups())
        except:
            self.error("Unable to read /proc/mounts")

        return self.mount_db

    def mount_point_to_mount_dev(self,mount_point):
        return self.build_mount_db()['mount_point'].get(mount_point,None)

    def mount_dev_to_mount_point(self,mount_dev):
        return self.build_mount_db()['mount_dev'].get(mount_dev,None)

    @property
    def is_mounted(self):
        return self.mount_point_to_mount_dev(self.real_mount_point) == \
               self.parent_device

    @property
    def is_mounted_by_something(self):
        return self.mount_point_to_mount_dev(self.real_mount_point) is not None

    @property
    def is_mounted_by_other(self):
        return not self.is_mounted and self.is_mounted_by_something

    @property
    def mount_device(self):
        return self.mount_point_to_mount_dev(self.real_mount_point)

    def do_mount(self):
        cmd = [self.mount_cmd, '-r', self.parent_device, self.mount_point]
        (res,stdout,stderr) = self.run_cmd(cmd)
        self.build_mount_db(rebuild=True)
        if not res:
            self.error("Mount command failed:  %s" % stderr)

    def do_umount(self):
        cmd = [self.umount_cmd, self.mount_point]
        (res,stdout,stderr) = self.run_cmd(cmd)
        self.build_mount_db(rebuild=True)
        if not res:
            self.error("Mount command failed:  %s" % stderr)

    @property
    def is_setup(self):
        return self.is_mounted


    def safe_set_up(self):
        self.infomsg("Mounting device %s onto %s" %
                         (self.parent_device, self.mount_point))
            
        # sanity check:  if device already mounted, nothing to do
        if self.is_mounted:
            self.infomsg("Device already mounted; nothing to do\n")
            return
        self.debugmsg("  Sanity check passed:  device not already mounted")

        # sanity check:  device exists (wait up to two seconds for device
        # to appear)
        if not self.device_exists_wait(20):
            self.error("Cannot mount non-existent device %s" %
                       self.parent_device)
        self.debugmsg("  Sanity check passed:  device exists")

        # sanity check:  ensure mount point exists
        if not self.mount_point_exists:
            self.error("Mount point non-existent, and failed to create: %s" %
                       self.mount_point)
        self.debugmsg("  Sanity check passed:  mount point exists")

        # sanity check:  ensure mount point is a directory
        if not self.mount_point_is_directory:
            self.error("Mount point exists but is not a directory")
        self.debugmsg("  Sanity check passed:  mount point is a directory")

        # sanity check:  ensure mount point is not already mounted upon
        if self.is_mounted_by_other:
            self.error("Mount point already mounted upon")
        self.debugmsg("  Sanity check passed:  "
                      "mount point not already mounted upon")

        # do the mount
        self.do_mount()
        self.infomsg("  Ran 'mount' command")

        # sanity check:  ensure device is now mounted
        if not self.is_mounted:
            self.error("Device is not mounted")
        self.infomsg("Device successfully mounted\n")

    def safe_teardown(self):
        self.infomsg("Unmounting directory %s" % self.parent_device)

        # sanity check:  if mount point not mounted upon, nothing to do
        if not self.is_mounted_by_something:
            self.infomsg("Mount point not mounted upon; nothing to do\n")
            return
        self.debugmsg("  Sanity check passed:  mount point is mounted upon")

        # do the umount
        self.do_umount()
        self.infomsg("  Ran 'umount' command")

        # remove the mount directory
        self.remove_mount_point()

        # sanity check:  ensure device is now unmounted
        if self.is_mounted_by_something:
            self.error("Device is still mounted; umount failed")
        self.infomsg("Device successfully unmounted\n")


# Register this layer
Stack.register_layer(MountPartition)
