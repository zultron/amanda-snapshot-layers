# Utility functions

import sys, re

from subprocess import Popen, PIPE
from datetime import datetime


class Util(object):
    sudo_fail_re = re.compile(r'sudo:.*password')
    # parameters shared across instances
    parms = { 'log' : None,
              }

    def __init__(self, debug=False,
                 logfile=None,
                 log_to_stdout=False,
                 ):

        # This is set per instance
        self.debug = debug

        # The following 'parms' keys are shared between instances;
        # don't touch them at all by default, since this method will
        # be called multiple times
        
        # By default, log to stdout
        if log_to_stdout or self.parms['log'] is None:
            self.parms['log'] = sys.stdout;
        elif logfile:
            self.parms['log'] = open(logfile, 'w')

    @property
    def error_prefix(self):
        if self.params.action in ('amcheck', 'estimate'):
            return 'ERROR'
        elif self.params.action in ('backup'):
            return '?'
        else:
            return ''

    @property
    def success_prefix(self):
        if self.params.action == 'amcheck':
            return 'OK'
        elif self.params.action == 'backup':
            return '|'
        elif self.params.action == 'estimate':
            # In Script_App.pm, only the 'check' action prints 'OK' messages
            return None
        else:
            return ''

    def infomsg(self,msg):
        for line in msg.split('\n'):
            self.parms['log'].write("%s\n" % line)

    def debugmsg(self,msg):
        if self.debug:
            self.infomsg(msg)

    def statusmsg(self,msg,error=False):
        if error:
            prefix = self.error_prefix
        else:
            prefix = self.success_prefix
        if prefix is None:
            return
        for line in [ "%s %s\n" % (prefix, l) for l in msg.split('\n') ]:
            self.parms['log'].write(line)
            if self.parms['log'] is not sys.stdout:
                sys.stdout.write(line)

    def error(self,msg):
        self.statusmsg(msg, error=True)
        sys.exit(1)

    def _print_io(self,prefix,output,debug=True):
        for line in [l for l in output.rstrip().split('\n') if l]:
            if debug:
                self.debugmsg(prefix + line)
            else:
                self.infomsg(prefix + line)

    def run_cmd(self,cmd,sudo=True,t_f=True,fail_abort=True):
        # cmd may be a string (bad) or an array (good)
        if type(cmd) is str:
            cmd = cmd.split()
        if sudo:
            cmd = ['sudo', '-n'] + cmd

        # run cmd, capturing stdin, stdout and exit status
        self.debugmsg("        Running command:  %s" % ' '.join(cmd))
        popen_obj = Popen(cmd, stdout=PIPE, stderr=PIPE)
        (stdout, stderr) = popen_obj.communicate()

        # when t_f is True, return True/False; otherwise, integer exit status
        if t_f:
            res = popen_obj.returncode == 0
        else:
            res = popen_obj.returncode

        # when running sudo, if the sudo command fails,
        #   if fail_abort is True, print debug messages and error out;
        #   otherwise, return None for calling routine to handle
        if sudo and self.sudo_fail_re.match(stderr):
            if fail_abort:
                self.infomsg("Command failed, aborting:")
                self.infomsg("              exit:  %s" % popen_obj.returncode)
                self._print_io("            stdout:  ", stdout)
                self._print_io("            stderr:  ", stderr)
                sys.exit(1)
            else:
                res = None

        # print debugging info
        self.debugmsg("            exit/return:  %s/%s" %
                      (popen_obj.returncode,res))
        self._print_io("            stdout:  ", stdout, debug=True)
        self._print_io("            stderr:  ", stderr, debug=True)

        return (res,stdout,stderr)


