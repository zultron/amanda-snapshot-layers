# RBD volumes

#FIXME
from pprint import pformat

import re

have_rbd = True
try:
    import rados
    import rbd
except:
    have_rbd = False

from stack import Stack
from layers import SnapLayer
from params import Params

Params.add_option(
    "--ceph_conf", "--ceph-conf",
    default="/etc/ceph/ceph.conf",
    help=("Ceph configuration file"))


# Decorator for RBD functions: ensure image is defined
def rbd_method(func):
    def wrapper(obj, *args,**kwargs):
        if obj.cluster is None:
            with rados.Rados(conffile=obj.ceph_conf) as cluster:
                with cluster.open_ioctx(obj.ceph_pool) as ioctx:
                    with rbd.Image(ioctx, obj.rbd_volume) as image:
                        obj.debugmsg(
                            "      %s:  Setting cluster, ioctx and image" %
                            func.func_name)
                        obj.set_ceph_objects(cluster,ioctx,image)
                        res = func(obj,*args,**kwargs)
                        obj.debugmsg(
                            "      %s:  Clearing cluster, ioctx and image" %
                            func.func_name)
                        obj.clear_ceph_objects()
                        return res
        else:
            return func(obj,*args,**kwargs)
    return wrapper



class RBDSnapLayer(SnapLayer):
    '''
    Given an RBD name-label and snapshot name, create a snapshot

    Stack example, partition 2 on the RBD volume 'rbd/vm.img':
    /mnt/amanda/rbd=rbd+vm.img,part=2

    Args will be [ ceph_pool, rbd_volume ]
    '''

    name = 'rbd'
    rbd_snap_re = re.compile(r'^[^/@]+/[^/@]+@[^/@]+$')

    ceph_objects = {}

    def __init__(self, *args):
        super(RBDSnapLayer, self).__init__(*args)
        self.snap_name = self.params.snap_suffix

    @property
    def cluster(self):
        return self.ceph_objects.get('cluster',None)

    @property
    def ioctx(self):
        return self.ceph_objects.get('ioctx',None)

    @property
    def image(self):
        return self.ceph_objects.get('image',None)

    def set_ceph_objects(self,cluster,ioctx,image=None):
        self.ceph_objects = {'cluster' : cluster,
                             'ioctx' : ioctx,
                             'image' : image }

    def clear_ceph_objects(self):
        self.ceph_objects = {}

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
    def ceph_conf(self):
        return self.params.ceph_conf

    @property
    def ceph_pool(self):
        return self.args[0]

    @property
    def rbd_volume(self):
        return self.args[1]

    @property
    def orig_device(self):
        return '%s/%s' % (self.ceph_pool, self.rbd_volume)

    @property
    def device(self):
        return '%s/%s@%s' % \
            (self.ceph_pool, self.rbd_volume, self.snap_name)

    @rbd_method
    def _snap_exists(self):
        for s in self.image.list_snaps():
            if s['name'] == self.snap_name:
                self.debugmsg(
                    "    found snapshot '%s', id %s, size %s" %
                    (self.device,s['id'],s['size']))
                return True
        self.debugmsg("    RBD image '%s' has no snap '%s'" %
                      (self.orig_device, self.snap_name))
        return False

    @property
    def snap_exists(self):
        try:
            return self._snap_exists()
        except rbd.ImageNotFound:
            return False

    @rbd_method
    def _orig_exists(self):
        pass

    @property
    def orig_exists(self):
        try:
            self._orig_exists()
            return True
        except rbd.ImageNotFound:
            return False

    @property
    def is_snapshot(self):
        '''
        Sanity check: Device is a snapshot; just a check on the name
        is sufficient, no need to see if it actually exists
        '''
        return self.rbd_snap_re.match(self.device) is not None

    @property
    def matches_target(self):
        self.debugmsg("    matches_target:  skipping sanity test")
        return True

    @rbd_method
    def create_snapshot(self):
        self.debugmsg("  Creating RBD snapshot '%s' for image '%s'" %
                      (self.orig_device,self.snap_name))
        self._create()
        self.debugmsg("  Protecting RBD snapshot")
        self._protect()

    @rbd_method
    def _create(self):
        self.image.create_snap(self.snap_name)

    @property
    @rbd_method
    def _is_protected(self):
        '''
        Check if snapshot is protected
        '''
        res = self.image.is_protected_snap(self.snap_name)
        self.debugmsg(
            "    RBD snapshot protected:  %s" % res)
        return res
        
    @rbd_method
    def _protect(self):
        '''
        Protect snapshot for layering
        '''
        self.image.protect_snap(self.snap_name)
        

    @rbd_method
    def _unprotect(self):
        '''
        Protect snapshot for layering
        '''
        self.image.unprotect_snap(self.snap_name)
        
    @rbd_method
    def _remove(self):
        '''
        Remove snapshot
        '''
        self.image.remove_snap(self.snap_name)
        
    @rbd_method
    def remove_snapshot(self):
        if self._is_protected:
            self._unprotect()
        self._remove()

    # Set up the RBD objects once for all operations in safe_set_up
    @rbd_method
    def safe_set_up(self):
        super(RBDSnapLayer,self).safe_set_up()

    # Set up the RBD objects once for all operations in safe_teardown
    @rbd_method
    def safe_teardown(self):
        super(RBDSnapLayer,self).safe_teardown()


    @property
    @rbd_method
    def _children(self):
        '''
        Check snapshot children
        '''
        self.image.set_snap(self.snap_name)
        res = self.image.list_children()
        for c in res:
            self.debugmsg(
                "    RBD snapshot child:  %s/%s" % c)
        return res
        
    @property
    @rbd_method
    def _lockers(self):
        '''
        Check snapshot lockers
        '''
        res = self.image.list_lockers()
        for l in res:
            self.debugmsg(
                "    RBD snapshot locker:  %s %s %s" % l)
        return res
        

# Register this layer
if have_rbd:
    Stack.register_layer(RBDSnapLayer)
