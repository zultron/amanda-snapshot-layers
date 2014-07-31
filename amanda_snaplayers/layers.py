# Base Layer class and Snapper subclass

import sys, os.path, pickle
from datetime import datetime, timedelta
from pprint import pformat

from util import Util
from params import Params


# Snapshot parameters
Params.add_option(
    "--stale_seconds", "--stale-seconds", type="int",
    required_param=True, interesting_param=True,
    help=("number of seconds before a snapshot is considered stale"))
Params.add_option(
    "--size",
    required_param=True, interesting_param=True,
    help=("size of snapshot; see lvcreate(8) for units"))
Params.add_option(
    "--snaplayers_state_file", "--snaplayers-state-file",
    default='/var/lib/amanda/snaplayers.db',
    help=("location of snaplayers state file"))



class Snapdb(dict):
    '''
    pickled dict of snapshot creation timestamps persisted to a file
    '''

    epoch = datetime(1971,01,01)

    def __init__(self,debug=False,state_file=None):
        self.state_file = state_file
        self.util = Util()
        if os.path.exists(self.state_file):
            try:
                self.update(pickle.load(open(self.state_file, 'r')))
            except:
                self.util.error("Error reading snapshot db '%s': %s" %
                      (self.state_file, sys.exc_info()[0]))
        self.util.debugmsg("Read pickled DB: %s" % pformat(self))

    def save(self):
        try:
            pickle.dump(self,open(self.state_file, 'w'))
        except:
            self.util.error("Error writing snapshot db '%s':\n%s" %
                            (self.state_file, sys.exc_info()[0]))

    def record_snap(self,snap_device):
        self.setdefault(snap_device,{})['timestamp'] = datetime.now()
        self.save()

    def delete_snap(self,snap_device):
        self[snap_device] = {}
        self.save()

    def timestamp(self,device,set_default=False):
        if self.setdefault(device,{}).has_key('timestamp'):
            return self[device]['timestamp']
        else:
            if set_default:
                return self.epoch
            else:
                return None

    def is_expired(self,device,stale_seconds,nodefault=False):
        if not nodefault and self.timestamp(device) is None:
            return None
        else:
            return (datetime.now() - timedelta(seconds=stale_seconds)) > \
                   self.timestamp(device,True)
           

class Layer(Util):
    class_params = {}

    def __init__(self, arg_str, params, parent_layer):

        super(Layer, self).__init__(
            debug = params.debug)

        self.arg_str = arg_str
        self.params = params
        self.parent = parent_layer

    @property
    def parent_device(self):
        return self.parent.device

    @property
    def is_stale(self):
        if self.parent_device is None:
            self.error("class %s does not implement is_stale method" %
                       self.__class__.__name__)
        return self.parent.is_stale
    
    @property
    def is_setup(self):
        self.error("class %s does not implement is_setup method" %
                       self.__class__.__name__)
    
    def safe_teardown(self):
        self.error("class %s does not implement safe_teardown method" %
                       self.__class__.__name__)

    def safe_setup(self):
        self.error("class %s does not implement safe_setup method" %
                       self.__class__.__name__)


class Snapper(Layer):
    lvcreate = '/usr/sbin/lvcreate'
    lvremove = '/usr/sbin/lvremove'
    lvdisplay = '/usr/sbin/lvdisplay'
    snap_suffix = '.amsnap'
    name = 'lvm'

    class_params = {
        'snapdb' : None,
        }

    def print_info(self):
        self.infomsg("Initialized LVM snapshot object parameters:")
        self.infomsg("    target device = %s" % self.lv_device)
        self.infomsg("    snapshot device = %s" % self.device)
        self.infomsg("    stale seconds = %d" % self.stale_seconds)
        self.infomsg("    snapshot size = %s" % self.size)


    @property
    def snapdb(self):
        if self.class_params['snapdb'] is None:
            self.class_params['snapdb'] = \
                Snapdb(debug = self.debug,
                       state_file = self.params.state_file)
        return self.class_params['snapdb']

    @property
    def stale_seconds(self):
        return self.params.stale_seconds

    @property
    def size(self):
        return self.params.size

    @property
    def vg_name(self):
        return self.arg_str.split(self.params.field_sep)[0]

    @property
    def lv_name(self):
        return self.arg_str.split(self.params.field_sep)[1]

    @property
    def lv_device(self):
        return "/dev/%s/%s" % (self.vg_name, self.lv_name)
        

    @property
    def device(self):
        return self.lv_device + self.snap_suffix

    @property
    def snap_exists(self):
        cmd = [self.lvdisplay, '-c', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        return res

    @property
    def orig_exists(self):
        cmd = [self.lvdisplay, '-c', self.lv_device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        return res

    @property
    def is_snapshot(self):
        cmd = ['lvs', '--noheadings', '-o', 'lv_attr', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        return stdout.lstrip().rstrip().lower()[0] == 's'

    @property
    def matches_target(self):
        cmd = ['lvs', '--noheadings', '-o', 'origin', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        return stdout.lstrip().rstrip() == self.lv_name

    @property
    def is_stale(self, nodefault=False):
        return self.snapdb.is_expired(self.device, self.stale_seconds)

    @property
    def in_snapdb(self):
        return self.snapdb.is_expired(self.device,
                                      self.stale_seconds,
                                      nodefault=True) is not None

    @property
    def is_setup(self):
        # no sanity checks here, just if the snap exists or not;
        # good enough to know if tearing down is needed
        return self.snap_exists

    def create_snapshot(self):
        cmd = [self.lvcreate, '-s', '-n', self.device,
               '-L', self.size, self.lv_device]
        (res,stdout,stderr) = self.run_cmd(cmd)

        self.snapdb.record_snap(self.device)

        self.infomsg("  Ran 'lvcreate' command")
        
    def remove_snapshot(self):
        # delete the snapshot
        cmd = [self.lvremove, '-f', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)

        self.snapdb.delete_snap(self.device)

        self.infomsg("  Ran 'lvremove' command")

    def safe_set_up(self):

        self.infomsg("Setting up snapshot")
        not_exist=False

        # sanity check:  the original disk should exist
        if not self.orig_exists:
            self.error("target LV does not exist:  %s" %
                       self.lv_device)
        self.debugmsg("  Sanity check passed:  target LV exists")

        # Existing snapshots need sanity and staleness checks
        if self.snap_exists:
            self.infomsg("Found existing snapshot %s" % self.device)

            # sanity check:  existing snapshot's origin must be target device
            if not self.matches_target:
                self.error("Existing snapshot's origin is not target device; "
                           "aborting")
            self.debugmsg("  Sanity check passed:  "
                          "snapshot's origin matches target")

            # sanity check:  existing snapshots must be in db
            if not self.in_snapdb:
                self.error("Existing snapshot not found in database; aborting")
            self.debugmsg("  Sanity check passed:  snapshot found in database")

            # sanity check:  snapshots should be snapshots!
            if not self.is_snapshot:
                self.error("Device %s is not a snapshot; aborting" %
                           self.device)
            self.debugmsg("  Sanity check passed:  snapshot is a snapshot device")

            # remove stale snapshots
            if self.is_stale:
                self.infomsg("Snapshot is stale")
                # FIXME unimplemented; for now, just abort
                self.error("delete_snapshot() not implemented; aborting")
                #unmount_and_remove_snapshot(util, snapper)
        else:
            not_exist = True
            self.debugmsg("  Sanity check passed:  "
                          "Snapshot does not already exist")

        # Create snapshot if it doesn't exist (or was expired)
        if not_exist or not self.snap_exists:
            self.create_snapshot()
            # Check one last time
            if not self.snap_exists:
                self.error("Failed to create snapshot; aborting")

        self.infomsg("Snapshot successfully set up\n")

    def safe_teardown(self):

        self.infomsg("Removing snapshot")

        # sanity check:  snapshot should exist
        if not self.snap_exists:
            self.infomsg("Snapshot does not exist; not removing")
            return
        self.debugmsg("  Sanity check passed:  snapshot exists")

        # Sanity check: check target really is a snapshot
        if not self.is_snapshot:
            self.error("Snapshot is not a snapshot device; aborting")
        self.debugmsg("  Sanity check passed:  snapshot is a snapshot device")

        # Remove snapshot
        self.remove_snapshot()

        # Check one last time
        if self.snap_exists:
            self.error("Failed to remove snapshot; aborting")
        else:
            self.infomsg("Successfully removed snapshot\n")



