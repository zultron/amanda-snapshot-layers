# RBD volumes

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

Params.add_option(
    "--rbd_clone_suffix", "--rbd-clone-suffix",
    default=".amclone",
    help=("RBD clone image name suffix"))


# Decorators for Ceph functions: ensure cluster, ioctx and image are defined
def ceph_method(func,with_image=False):
    def wrapper(obj, *args,**kwargs):
        if obj.ceph_object_counts['cluster'] == 0:
            obj.ceph_objects['cluster'] = \
                rados.Rados(conffile=obj.ceph_conf)
            obj.ceph_objects['cluster'].connect()
            obj.debugmsg(
                "      %s:  Set ceph cluster" %
                func.func_name)
        obj.ceph_object_counts['cluster'] += 1
        try:
            if obj.ceph_object_counts['ioctx'] == 0:
                obj.ceph_objects['ioctx'] = \
                    obj.ceph_objects['cluster'].open_ioctx(obj.ceph_pool)
                obj.debugmsg(
                    "      %s:  Set ceph ioctx" %
                    func.func_name)
            obj.ceph_object_counts['ioctx'] += 1
            try:
                if with_image:
                    if obj.ceph_object_counts['image'] == 0:
                        obj.ceph_objects['image'] = \
                            rbd.Image(obj.ceph_objects['ioctx'],
                                      obj.rbd_volume)
                        obj.debugmsg(
                            "      %s:  Set ceph image" %
                            func.func_name)
                    obj.ceph_object_counts['image'] += 1

                try:
                    res = func(obj,*args,**kwargs)

                finally:
                    if with_image:
                        obj.ceph_object_counts['image'] -= 1
                        if obj.ceph_object_counts['image'] == 0:
                            obj.ceph_objects['image'].close()
                            obj.debugmsg(
                                "      %s:  Closed ceph image" %
                                func.func_name)
            finally:
                obj.ceph_object_counts['ioctx'] -= 1
                if obj.ceph_object_counts['ioctx'] == 0:
                    obj.ceph_objects['ioctx'].close()
                    obj.debugmsg(
                        "      %s:  Closed ceph ioctx" %
                        func.func_name)
        except Exception, e:
            print "exception: %s" % e
            raise e
        finally:
            obj.ceph_object_counts['cluster'] -= 1
            if obj.ceph_object_counts['cluster'] == 0:
                obj.ceph_objects['cluster'].shutdown()
                obj.debugmsg(
                    "      %s:  Closed ceph cluster" %
                    func.func_name)
        return res
    return wrapper

def rbd_method(func):
    return ceph_method(func,True)


class CephSnapLayer(SnapLayer):
    '''
    Common class inherited by RBDSnapLayer and RBDCloneLayer
    '''

    # Methods used by the rbd_method decorator wrapper
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
        if image is None:
            attr = 'ceph_objects'
        else:
            attr = 'rbd_objects'
            setattr(self,attr,
                    {'cluster' : cluster,
                     'ioctx' : ioctx,
                     'image' : image })

    def clear_ceph_objects(self):
        self.ceph_objects = {}

    def clear_rbd_objects(self):
        self.rbd_objects = {}

    @property
    def ceph_conf(self):
        return self.params.ceph_conf

    @property
    def ceph_pool(self):
        return self.args[0]

    @property
    def snap_name(self):
        return self.params.snap_suffix


class RBDSnapLayer(CephSnapLayer):
    '''
    Given an RBD name-label and snapshot name, create a snapshot

    Stack example, partition 2 on the RBD volume 'rbd/vm.img':
    /mnt/amanda/rbd=rbd+vm.img,part=2

    Args will be [ ceph_pool, rbd_volume ]
    '''

    name = 'rbd_snap'
    rbd_snap_re = re.compile(r'^[^/@]+/[^/@]+@[^/@]+$')

    ceph_object_counts = {'cluster':0, 'ioctx':0, 'image':0}
    ceph_objects = {}

    def __init__(self, *args):
        super(RBDSnapLayer, self).__init__(*args)

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
        self.debugmsg(
            "    Unprotecting RBD snapshot '%s'" % self.device)
        self.image.unprotect_snap(self.snap_name)
        
    @rbd_method
    def _remove(self):
        '''
        Remove snapshot
        '''
        self.debugmsg(
            "    Removing RBD snapshot '%s'" % self.device)
        self.image.remove_snap(self.snap_name)
        
    @rbd_method
    def remove_snapshot(self):
        if self._is_protected:
            self._unprotect()
        self._remove()
        
    @property
    @rbd_method
    def snap_children(self):
        '''
        Check snapshot children
        '''
        self.image.set_snap(self.snap_name)
        res = self.image.list_children()
        if res:
            for c in res:
                self.debugmsg(
                    "    RBD snapshot child:  %s/%s" % c)
        else:
            self.debugmsg("    No children of RBD snapshot '%s' found" %
                          self.device)
        return res
        
    @ceph_method
    def clone(self,child_name):
        self.debugmsg(
            "    Cloning snapshot '%s@%s' into image '%s', pool '%s'" %
            (self.rbd_volume, self.snap_name, child_name, self.ceph_pool))
        rbd_inst = rbd.RBD()
        with self.cluster.open_ioctx(self.ceph_pool) as child_ioctx:
            with self.cluster.open_ioctx(self.ceph_pool) as parent_ioctx:
                rbd_inst.clone(parent_ioctx, self.rbd_volume, self.snap_name,
                               child_ioctx, child_name,
                               rbd.RBD_FEATURE_LAYERING)

    # Set up the RBD objects once for all operations in safe_set_up
    @rbd_method
    def safe_set_up(self):
        super(CephSnapLayer,self).safe_set_up()

    # Set up the RBD objects once for all operations in safe_teardown
    @rbd_method
    def safe_teardown(self):
        super(CephSnapLayer,self).safe_teardown()
        

# Register this layer
if have_rbd:
    Stack.register_layer(RBDSnapLayer)


class RBDCloneLayer(CephSnapLayer):
    '''
    Given an RBD name-label and snapshot name, create a clone of a
    snapshot

    Stack example, partition 2 on the RBD volume 'rbd/vm.img':
    /mnt/amanda/rbd=rbd+vm.img,part=2

    Args will be [ ceph_pool, rbd_volume ]
    '''

    name = 'rbd_clone'
    insert_parent = 'rbd_snap'
    rbd_snap_re = re.compile(r'^[^/@]+/[^/@]+@[^/@]+$')

    ceph_object_counts = {'cluster':0, 'ioctx':0, 'image':0}
    ceph_objects = {'cluster':0, 'ioctx':0, 'image':0}

    @property
    def clone_suffix(self):
        return self.params.rbd_clone_suffix

    @property
    def args(self):
        '''
        Return the layer arg_str, like rbd+vm.img@amsnap, split
        into a list by the '+' and '@' characters
        '''
        
        return super(RBDCloneLayer,self).args + [self.clone_suffix]

    @property
    def rbd_volume(self):
        return "%s%s" % (self.args[1], self.args[2])

    @property
    def rbd_snap(self):
        return self.parent.rbd_snap

    @property
    def orig_device(self):
        return '%s/%s@%s' % (self.ceph_pool, self.args[1], self.snap_name)

    @property
    def device(self):
        return '%s/%s' % (self.ceph_pool, self.rbd_volume)

    @property
    def snap_exists(self):
        res = (self.ceph_pool, self.rbd_volume) in self.parent.snap_children
        if res:
            self.debugmsg(
                "    RBD image '%s' exists (child of '%s')" %
                (self.device, self.orig_device))
        else:
            self.debugmsg(
                "    No RBD image '%s' exists" % self.device)
        return res

    @property
    def orig_exists(self):
        return self.parent.snap_exists

    @property
    def is_snapshot(self):
        '''
        Sanity check:  Just do a string check
        '''
        return self.device.endswith(self.clone_suffix)

    def create_snapshot(self):
        self.debugmsg("  Cloning RBD snapshot '%s' into '%s'" %
                      (self.orig_device,self.device))
        self.parent.clone(self.rbd_volume)

    @ceph_method
    def remove_snapshot(self):
        # For debugging, list lockers
        self._lockers
        rbd_inst = rbd.RBD()
        self.debugmsg("  Removing RBD clone '%s'" % self.rbd_volume)
        try:
            rbd_inst.remove(self.ioctx, self.rbd_volume)
        except rbd.ImageBusy:
            self.error("Remove clone failed:  '%s' still has watchers" %
                       self.device)

    @property
    @rbd_method
    def _lockers(self):
        '''
        Check snapshot lockers
        '''
        res = self.image.list_lockers()
        if res:
            for l in res:
                self.debugmsg(
                    "    RBD snapshot locker:  %s %s %s" % l)
        else:
                self.debugmsg(
                    "    No RBD snapshot lockers found")
        return res
        

# Register this layer
if have_rbd:
    Stack.register_layer(RBDCloneLayer)
