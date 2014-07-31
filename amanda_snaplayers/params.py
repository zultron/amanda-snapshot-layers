# CLI parameters

from optparse import OptionParser
from time import localtime, strftime
from util import Util

class Params(object):

    required_params = ['stale_seconds', 'mount_base', 'size', 'device']
    optional_params = ['debug', 'log_to_stdout', 'config', 'host', 'disk',
                       'layer_param_field_sep', 'level', 'execute_where']
    all_params = required_params + optional_params
    interesting_params = ['device', 'disk', 'stale_seconds', 'mount_base',
                          'size', 'debug', 'log_to_stdout',
                          'layer_param_field_sep']

    def __init__(self,
                 set_up_entry_points,
                 tear_down_entry_points):

        self.set_up_entry_points = set_up_entry_points
        self.tear_down_entry_points = tear_down_entry_points

        # basic command line option parsing and sanity checks
        self.usage = "usage:  %prog [execute-on]+ [options]"
        self.parse_options()
        self.check_args()
        self.check_required_params()
        self.check_device_param()

        self.util = Util(debug=self.debug,
                         logfile = self.logfile,
                         log_to_stdout = self.log_to_stdout)


    def parse_options(self):
        parser = OptionParser(usage=self.usage)

        # custom properties
        parser.add_option("--stale_seconds", "--stale-seconds", type="int",
                          help=("number of seconds before a snapshot is "
                                "considered stale"))
        parser.add_option("--mount_base", "--mount-base",
                          help=("base directory to mount snapshot"))
        parser.add_option("--no_auto_mount", "--no-auto-monut",
                          help=("don't automatically try to automount the "
                                "final device; mount must be specified "
                                "explicitly"))
        parser.add_option("--size",
                          help=("size of snapshot; see lvcreate(8) for units"))
        parser.add_option("--debug", type="int",
                          help=("Print debug output; param is 0 or 1"))
        parser.add_option("--log_to_stdout", "--log-to-stdout",
                          action="store_true", default=False,
                          help=("output to stdout for debugging"))
        parser.add_option("--layer_param_field_sep", "--layer-param-field-sep",
                          default=',=+',
                          help=("separator charactors for "
                                "layers, params and fields (default ',=+')"))

        # standard properties
        parser.add_option("--device",
                          help=("mount directory with embedded device layering "
                                "scheme: <mount_base>/"
                                "(lvm=<vg+lv>|raid1|part=<part#>)[,<...>]/"))
        parser.add_option("--config",
                          help="amanda configuration")
        parser.add_option("--host",
                          help="client host")
        parser.add_option("--disk",
                          help="disk to back up")
        parser.add_option("--level", type="int",
                          help="dump level")
        parser.add_option("--execute_where", "--execute-where",
                          help="where this script is executed")

        (self.params, self.args) = parser.parse_args()
        self.parser = parser

        # link params into this object for convenience
        for p in self.all_params:
            try:
                setattr(self,p,getattr(self.params,p,None))
            except AttributeError:
                # can't set 'debug' attribute; it's a property defined below
                pass

    def check_args(self):
        if len(self.args) != 1:
            self.parser.error("must have exactly one arg; found %d" %
                              len(self.args))

    def check_required_params(self):
        for param in self.required_params:
            if not getattr(self.params, param):
                self.parser.error("Required parameter '%s' missing" % param)

    def check_device_param(self):
        if not self.device.startswith(
            self.params.mount_base + "/"):
            self.parser.error("device path must begin with "
                              "the base mount directory")

    def print_params(self):
        self.util.infomsg("\nCommand line argument parsing results:")
        for p in self.interesting_params:
            self.util.infomsg(" %25s: %s" % (p, getattr(self,p,None)))
        self.util.infomsg("\nScheme:")
        for layer in self.scheme:
            if len(layer) == 2:
                self.util.infomsg(" %-15s %s" % (layer[0], layer[1]))
            else:
                self.util.infomsg(" %s" % layer[0])
        self.util.infomsg("")
        
    @property
    def debug(self):
        return self.params.debug == 1

    @property
    def scheme(self):
        target_string = self.params.device[
            len(self.params.mount_base)+1:]

        # e.g. [['lvm', 'vg+lv'], ['raid1'], ['part', '1']]
        # (param values like for lvm are split within the params' respective
        # handling code)
        scheme = [i.split(self.layer_param_field_sep[1])
                  for i in target_string.split(self.layer_param_field_sep[0])]
        return scheme

    @property
    def field_sep(self):
        return self.layer_param_field_sep[2]

    @property
    def entry_point(self):
        return self.args[0].lower()

    @property
    def entry_point_split(self):
        return self.entry_point.split('-')

    @property
    def set_up_mode(self):
        return self.entry_point in self.set_up_entry_points

    @property
    def tear_down_mode(self):
        return self.entry_point in self.tear_down_entry_points

    @property
    def action(self):
        return self.entry_point_split[-1]

    @property
    def pre_post(self):
        return self.entry_point_split[1]

    @property
    def logfile(self):
        return '/var/log/amanda/amandad/lvsnap.%s.%s.%s.debug' % \
               (strftime("%Y%m%d%H%M%S", localtime()),
                self.params.disk, self.entry_point)


