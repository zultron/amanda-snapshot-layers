# Xen VDI snapshots

from stack import Stack
from layer_lv import LV

have_xenserver = True
try:
    import XenAPI, platform
except:
    have_xenserver = False

class XenVDISnapLayer(LV):
    '''
    Given a VDI name-label and snapshot name, create a snapshot

    /v/amanda.mount/xenvdi=junction.root.0,raid1,part=1
    '''

    name = 'xenvdi'

    def __init__(self,arg_str,params,parent_layer):

        super(XenVDISnapLayer,self).__init__(arg_str,params,parent_layer)

        if not have_xenserver:
            self.error("Tried to init XenVDISnapLayer, but XenAPI libs "
                       "not available")

        self.init_xenapi_session()

    def print_info(self):
        super(XenVDISnapLayer,self).print_info()
        self.infomsg("    VDI name-label = %s" % self.vdi_name_label)

        
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
    def orig_device(self):
        return '/dev/VG_XenStorage-%s/VHD-%s' % ( self.sr_record['uuid'],
                                                  self.vdi_record['uuid'] )
    

# Register this layer
if have_xenserver:
    Stack.register_layer('xenvdi',XenVDISnapLayer)
