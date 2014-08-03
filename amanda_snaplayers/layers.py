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
    interesting_param=True,
    help=("size of snapshot; see lvcreate(8) for units"))
Params.add_option(
    "--snaplayers_state_file", "--snaplayers-state-file",
    default='/var/lib/amanda/snaplayers.db',
    help=("location of snaplayers state file"))
Params.add_option(
    "--snap_suffix", "--snap-suffix",
    default='.amsnap',
    help=("snapshot suffix"))


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
    params = None
    class_params = {}

    def __init__(self, arg_str, params, parent_layer):

        super(Layer, self).__init__(
            debug = params.debug)

        self.arg_str = arg_str
        self.params = params
        self.parent = parent_layer

    # inheriting classes must implement at least these methods:
    # is_setup (property), safe_teardown, safe_setup

    @property
    def args(self):
        '''
        Return the layer arg_str, like rbd+amanda0.root.img.new, split
        into a list by the '+' character
        '''
        return self.arg_str.split(self.params.field_sep)

    @property
    def parent_device(self):
        return self.parent.device

    @property
    def is_stale(self):
        if self.parent_device is None:
            self.error("class %s does not implement is_stale method" %
                       self.__class__.__name__)
        return self.parent.is_stale
    
    def device_partition(self,part_num):
        '''
        Return the device string for a partition; some layers may
        override this
        '''
        return '%s%s' % (self.device,part_num)

    def freshen(self):
        '''
        This method is called at each major entry point into the
        stack.  Layers may override this to call expensive freshening
        methods just once.
        '''
        pass

class SnapLayer(Layer):
    
    name = None
    class_params = {
        'snapdb' : None,
        }

    # inheriting classes must implement at least these methods:
    #
    # properties:
    # device, orig_device, snap_exists, orig_exists, is_setup, is_snapshot,
    # matches_target
    #
    # methods:
    # create_snapshot, remove_snapshot

    def print_info(self):
        if self.name is None:
            self.error("Class 'name' attribute not defined for class %s" %
                       self.__class__.__name__)
        self.infomsg("Initialized layer %s snapshot object parameters:" % \
                         self.name)
        self.infomsg("    target device = %s" % self.orig_device)
        self.infomsg("    snapshot device = %s" % self.device)
        self.infomsg("    stale seconds = %d" % self.stale_seconds)
        self.infomsg("    snapshot size = %s" % self.size)


    @property
    def snapdb(self):
        if self.class_params['snapdb'] is None:
            self.class_params['snapdb'] = \
                Snapdb(debug = self.debug,
                       state_file = self.params.snaplayers_state_file)
        return self.class_params['snapdb']

    @property
    def stale_seconds(self):
        return self.params.stale_seconds

    @property
    def size(self):
        return self.params.size

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

    def safe_set_up(self):

        self.infomsg("Setting up snapshot layer '%s'" % self.name)
        not_exist=False

        # freshen up the layer
        self.freshen()

        # sanity check:  the original disk should exist
        if not self.orig_exists:
            self.error("target device does not exist:  %s" %
                       self.orig_device)
        self.debugmsg("  Sanity check passed:  target device exists")

        if self.snap_exists:
            # Existing snapshots need sanity and staleness checks
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
            else:
                self.debugmsg("  Sanity check passed:  "
                              "Snapshot successfully created")
            # Record snapshot
            self.snapdb.record_snap(self.device)

        self.infomsg("Snapshot successfully set up\n")


    def safe_teardown(self):

        self.infomsg("Removing snapshot layer '%s'" % self.name)

        # freshen up the layer
        self.freshen()

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
            self.error("Snapshot still exists after removal attempt; aborting")
        else:
            self.infomsg("Successfully removed snapshot\n")

        # Record removal
        self.snapdb.delete_snap(self.device)

