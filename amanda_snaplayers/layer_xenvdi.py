# Xen VDI snapshots

from stack import Stack
from layers import Snapper

have_xenserver = True
try:
    import XenAPI, platform
except:
    have_xenserver = False

class XenVDISnapper(Snapper):
    '''
    Given a VDI name-label and snapshot name, create a snapshot

    /v/amanda.mount/xenvdi=junction.root.0,raid1,part=1
    '''

    def __init__(self,arg_str,params,parent_layer):

        super(XenVDISnapper,self).__init__(arg_str,params,parent_layer)

        if not have_xenserver:
            self.error("Tried to init XenVDISnapper, but XenAPI libs "
                       "not available")

        self.init_xenapi_session()

    def print_info(self):
        self.infomsg("Initialized Xen VDI snapshot object parameters:")
        self.infomsg("    VDI name-label = %s" % self.vdi_name_label)
        self.infomsg("    target device = %s" % self.lv_device)
        self.infomsg("    snapshot device = %s" % self.device)
        self.infomsg("    stale seconds = %d" % self.stale_seconds)
        self.infomsg("    snapshot size = %s" % self.size)

        
    def init_xenapi_session(self):
        self.session = XenAPI.xapi_local()
        self.session.xenapi.login_with_password('root', '')
        #self.session = XenAPI.Session('http://%s' % self.hostname)
        #session.xenapi.login_with_password(self.username, self.password)

    @property
    def vdi_name_label(self):
        return self.arg_str

    @property
    def vdi_record(self):
        for (key, val) in self.session.xenapi.VDI.get_all_records().items():
            if val['name_label'] == self.vdi_name_label:
                return val
        return None

    @property
    def sr_record(self):
        try:
            sr = self.session.xenapi.SR.get_record(self.vdi_record['SR'])
        except Exception, e:
            self.error("Unable to get SR:  %s" % e)
        return sr

    @property
    def lv_device(self):
        return '/dev/VG_XenStorage-%s/VHD-%s' % ( self.sr_record['uuid'],
                                                  self.vdi_record['uuid'] )
    

# Register this layer
Stack.register_layer('xenvdi',XenVDISnapper)
