# LVM layer snapshots

from stack import Stack
from layers import SnapLayer

class LV(SnapLayer):
    lvcreate = '/usr/sbin/lvcreate'
    lvremove = '/usr/sbin/lvremove'
    lvdisplay = '/usr/sbin/lvdisplay'
    snap_suffix = '.amsnap'
    name = 'lv'

    @property
    def vg_name(self):
        return self.arg_str.split(self.params.field_sep)[0]

    @property
    def lv_name(self):
        return self.arg_str.split(self.params.field_sep)[1]

    @property
    def orig_device(self):
        return "/dev/%s/%s" % (self.vg_name, self.lv_name)

    @property
    def device(self):
        return self.orig_device + self.snap_suffix

    @property
    def snap_exists(self):
        cmd = [self.lvdisplay, '-c', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)
        return res

    @property
    def orig_exists(self):
        cmd = [self.lvdisplay, '-c', self.orig_device]
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

    def create_snapshot(self):
        cmd = [self.lvcreate, '-s', '-n', self.device,
               '-L', self.size, self.orig_device]
        (res,stdout,stderr) = self.run_cmd(cmd)

        self.infomsg("  Ran 'lvcreate' command")
        
    def remove_snapshot(self):
        # delete the snapshot
        cmd = [self.lvremove, '-f', self.device]
        (res,stdout,stderr) = self.run_cmd(cmd)

        self.infomsg("  Ran 'lvremove' command")

Stack.register_layer(LV)
