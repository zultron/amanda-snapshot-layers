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


