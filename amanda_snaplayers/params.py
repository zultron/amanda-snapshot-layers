# CLI parameters

from optparse import OptionParser
from time import localtime, strftime
from util import Util

# Default log file pattern
LOG_FILE_PAT = '/var/log/amanda/amandad/lvsnap.' \
    '%(timestamp)s.%(disk)s.%(entry_point)s.debug'


class Params(object):

    required_params = ['stale_seconds', 'mount_base', 'size', 'device']
    optional_params = ['debug', 'log_to_stdout', 'config', 'host', 'disk',
                       'layer_param_field_sep', 'level', 'execute_where']
    all_params = required_params + optional_params
    interesting_params = ['device', 'disk', 'stale_seconds', 'mount_base',
                          'size', 'debug', 'log_to_stdout',
                          'layer_param_field_sep']

    # Make this a class property so other modules can add options
    options = OptionParser(
        usage="usage:  %prog [execute-on]+ [options]",
        description="Amanda backup script plugin for backing up " \
            "volume snapshots",
        epilog="See the README file or " \
            "https://github.com/zultron/amanda-snapshot-layers " \
            "for more information"
        )

    def __init__(self,
                 set_up_entry_points,
                 tear_down_entry_points):

        self.set_up_entry_points = set_up_entry_points
        self.tear_down_entry_points = tear_down_entry_points

        # basic command line option parsing and sanity checks
        self.parse_options()
        self.check_args()
        self.check_required_params()
        self.check_device_param()

        self.util = Util(debug=self.debug,
                         logfile = self.logfile,
                         log_to_stdout = self.log_to_stdout)


    def parse_options(self):
        # custom properties
        self.options.add_option(
            "--mount_base", "--mount-base",
            help=("base directory to mount snapshot"))
        self.options.add_option(
            "--debug", type="int",
            help=("Print debug output; param is 0 or 1"))
        self.options.add_option(
            "--log_to_stdout", "--log-to-stdout",
            action="store_true", default=False,
            help=("output to stdout for debugging"))
        self.options.add_option(
            "--layer_param_field_sep", "--layer-param-field-sep",
            default=',=+',
            help=("separator charactors for layers, params and fields "
                  "(default ',=+')"))
        self.options.add_option(
            "--snaplayers_log_pattern", "--snaplayers-log-pattern",
            default=LOG_FILE_PAT,
            help=("snapshot log file pattern; default: %s" % LOG_FILE_PAT))

        # standard properties
        self.options.add_option(
            "--device",
            help=("mount directory with embedded device layering scheme: "
                  "<mount_base>/(lvm=<vg+lv>|raid1|part=<part#>)[,<...>]/"))
        self.options.add_option(
            "--config",
            help="amanda configuration")
        self.options.add_option(
            "--host",
            help="client host")
        self.options.add_option(
            "--disk",
            help="disk to back up")
        self.options.add_option(
            "--level", type="int",
            help="dump level")
        self.options.add_option(
            "--execute_where", "--execute-where",
            help="where this script is executed")

        (self.params, self.args) = self.options.parse_args()

        # link params into this object for convenience
        for p in self.all_params:
            try:
                setattr(self,p,getattr(self.params,p,None))
            except AttributeError:
                # can't set 'debug' attribute; it's a property defined below
                pass

    def check_args(self):
        if len(self.args) != 1:
            self.options.error("must have exactly one arg; found %d" %
                               len(self.args))

    def check_required_params(self):
        for param in self.required_params:
            if not getattr(self.params, param):
                self.options.error("Required parameter '%s' missing" % param)

    def check_device_param(self):
        if not self.device.startswith(
            self.params.mount_base + "/"):
            self.options.error("device path must begin with "
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
        return self.params.snaplayers_log_pattern % \
               { 'timestamp' : strftime("%Y%m%d%H%M%S", localtime()),
                 'disk' : self.params.disk,
                 'entry_point' : self.entry_point,
                 }

