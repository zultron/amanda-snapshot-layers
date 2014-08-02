# Libvirt volumes attached to an amanda server VM

from stack import Stack
from layers import SnapLayer
from params import Params

have_libvirt = True
try:
    import libvirt
except:
    have_libvirt = False

import os.path,platform,time
from lxml import etree
from pprint import pformat

Params.add_option(
    "--qemu_url", "--qemu-url",
    default="qemu:///system",
    help=("qemu URL"))

Params.add_option(
    "--libvirt_auth_file", "--libvirt-auth-file",
    default="/var/lib/amanda/libvirt-authfile",
    help=("Libvirt authentication file"))

Params.add_option(
    "--libvirt_vm_hostname", "--libvirt-vm-hostname",
    help=("Amanda server VM name"))

Params.add_option(
    "--ceph_auth_user", "--ceph-auth-user",
    default="admin",
    help=("Ceph user"))

Params.add_option(
    "--libvirt_secret_uuid", "--libvirt-secret-uuid",
    help=("Libvirt storage secret UUID"))

Params.add_option(
    "--disk_device_prefix", "--disk-device-prefix",
    default='/dev/vd',
    help=("Attached disk device filename prefix; default '/dev/vd'"))

Params.add_option(
    "--libvirt_attach_timeout", "--libvirt-attach-timeout",
    type="int", default=30,
    help=("Maximum time to wait for a libvirt volume to be attached "
          "to the backup VM"))


class LibvirtVolLayer(SnapLayer):
    '''
    This is Ceph specific, since I don't have other volumes to
    generalize with.

    Given a Ceph volume, create a ceph clone (in lower layers) and
    attach to the backup host.

    Stack example, partition 2 on the RBD volume 'rbd/vm.img':
    /mnt/amanda/libvirt=rbd+vm.img,part=2

    Args will be [ ceph_pool, rbd_volume ]
    '''

    name = 'libvirt'
    insert_parent = 'rbd_clone'
    ceph_vol_xml_template = '''
        <disk type='network' device='disk'>
          <driver name='qemu' type='raw'/>
          <auth username='%(username)s'>
            <secret type='ceph' uuid='%(secret_uuid)s'/>
          </auth>
          <source protocol='rbd' name='%(pool)s/%(volume)s'/>
          <target dev='%(device)s' bus='virtio'/>
        </disk>
        '''


    @property
    def qemu_url(self):
        if self.params.libvirt_auth_file is not None:
            return "%s?authfile=%s" % \
                (self.params.qemu_url, self.params.libvirt_auth_file)
        else:
            return self.params.qemu_url

    @property
    def libvirt_conn(self):
        '''
        Connection to libvirtd
        '''
        if not hasattr(self,'_libvirt_conn'):
            self._libvirt_conn = libvirt.open(self.qemu_url)
            self.debugmsg("    Set up libvirt connection to '%s'" %
                          self.params.qemu_url)
        return self._libvirt_conn

    @property
    def libvirt_vm_hostname(self):
        '''
        The Amanda server VM hostname
        '''
        if self.params.libvirt_vm_hostname is not None:
            return self.params.libvirt_vm_hostname
        else:
            # WAG:  VM hostname is first component of hostname
            return platform.node().split('.')[0]

    @property
    def libvirt_vm(self):
        if not hasattr(self,'_libvirt_vm'):
            self._libvirt_vm = \
                self.libvirt_conn.lookupByName(self.libvirt_vm_hostname)
            self.debugmsg("    Set up libvirt object for vm '%s'" %
                          self.libvirt_vm_hostname)
        return self._libvirt_vm

    @property
    def libvirt_vm_xml(self):
        return etree.XML(self.libvirt_vm.XMLDesc(0))

    @property
    def libvirt_storage_pool_name(self):
        return self.args[0]

    @property
    def libvirt_storage_pool(self):
        if not hasattr(self,'_libvirt_storage_pool'):
            self._libvirt_storage_pool = (
                self.libvirt_conn.storagePoolLookupByName(
                    self.libvirt_storage_pool_name))
            self.debugmsg("    Set up libvirt object for storage pool '%s'" %
                          self.libvirt_storage_pool_name)
        return self._libvirt_storage_pool

    def libvirt_storage_pool_refresh(self):
        self.debugmsg("    Refreshing storage pool")
        self.libvirt_storage_pool.refresh(0)

    @property
    def libvirt_storage_pool_volume_list(self):
        return self.libvirt_storage_pool.listVolumes()

    @property
    def libvirt_storage_volume_name(self):
        return self.parent.rbd_volume

    @property
    def libvirt_storage_volume(self):
        if not hasattr(self,'_libvirt_storage_volume'):
            try:
                self._libvirt_storage_volume = (
                    self.libvirt_storage_pool.storageVolLookupByName(
                        self.libvirt_storage_volume_name))
            except libvirt.libvirtError, e:
                self.error("Failed to find volume '%s' in pool '%s'" %
                           (self.libvirt_storage_volume_name,
                            self.libvirt_storage_pool_name))
            self.debugmsg(
                "    Set up libvirt object for storage volume '%s'" %
                self.libvirt_storage_volume_name)
        return self._libvirt_storage_volume

    @property
    def ceph_auth_user(self):
        return self.params.ceph_auth_user

    @property
    def livirt_secret_uuid(self):
        return self.params.libvirt_secret_uuid

    @property
    def mapped_device(self):
        '''
        Check to see if the orig_device is already mapped to an
        existing block device
        '''
        devs = [t.get('dev') for t in self.libvirt_vm_xml.xpath(
                "/domain/devices/disk/source[@name='%s']/../target" %
                self.orig_device)]
        # Check for weird cases
        if len(devs) > 1:
            self.error("Found multiple devices mapped to volume '%s': [%s]" %
                       (self.orig_device, ', '.join(devs)))
        # Return dev if found, otherwise None
        if devs:
            return devs[0]
        else:
            return None


    @property
    def disk_device(self):
        # There may be a race condition determining the new device
        # name to attach; reserving the device name should be
        # addressed here

        if not hasattr(self,'_disk_device'):
            # If a device already mapped, select that
            dev = self.mapped_device
            if dev is not None:
                self._disk_device = dev
                self.debugmsg("    Found existing VM device map to '%s'"
                              % dev)
            else:
                # Device pattern, e.g. 'vd%s', translating to /dev/vd?
                dev_pat = self.params.disk_device_prefix + '%s'
                if dev_pat.startswith('/dev/'):
                    # strip off initial '/dev/' for libvirt
                    dev_pat = dev_pat[5:]

                # Look for unused device
                for dev in [dev_pat%chr(ord('a')+i) for i in range(0,26)]:
                    if not os.path.exists('/dev/'+dev):
                        self._disk_device = dev
                        break
                else:
                    self.error("Unable to find free disk device '%s*'" %
                               self.params.disk_device_prefix)
                self.debugmsg(
                        "    Selected unused VM target device '%s'" %
                        self._disk_device)

        return self._disk_device

    @property
    def libvirt_storage_volume_xml(self):
        disk_info = {
            'username' : self.ceph_auth_user,
            'secret_uuid' : self.livirt_secret_uuid,
            'pool' : self.libvirt_storage_pool_name,
            'volume' : self.libvirt_storage_volume_name,
            'device' : self.disk_device,
            }
        return self.ceph_vol_xml_template % disk_info

    @property
    def libvirt_vm_rbd_volume_names(self):
        '''
        List of all RBD volume names attached to the backup VM
        '''
        return [s.get('name') for s in self.libvirt_vm_xml.xpath(
                "/domain/devices/disk/source[@protocol='rbd']")]

    def libvirt_storage_volume_attach(self):
        self.debugmsg(
            "    Attaching libvirt storage volume '%s' "
            "to local VM device '%s'" %
            (self.libvirt_storage_volume_name,
             self.libvirt_vm_hostname))
        try:
            res = self.libvirt_vm.attachDevice(self.libvirt_storage_volume_xml)
        except libvirt.libvirtError, e:
            self.error("Attaching pool '%s' volume '%s' to VM '%s': \n\t%s" %
                       (self.libvirt_storage_pool_name,
                        self.libvirt_storage_volume_name,
                        self.libvirt_vm_hostname,
                        e))

    def libvirt_storage_volume_detach(self):
        self.debugmsg(
            "    Detaching libvirt storage volume '%s' "
            "from local VM device '%s'" %
            (self.libvirt_storage_volume_name,
             self.libvirt_vm_hostname))
        try:
            res = self.libvirt_vm.detachDevice(self.libvirt_storage_volume_xml)
        except libvirt.libvirtError, e:
            self.error("Detaching pool '%s' volume '%s' from VM '%s': \n\t%s" %
                       (self.libvirt_storage_pool_name,
                        self.libvirt_storage_volume_name,
                        self.libvirt_vm_hostname,
                        e))


    @property
    def device(self):
        return '/dev/%s' % self.disk_device

    @property
    def orig_device(self):
        return self.parent.device

    @property
    def virsh_volume(self):
        return self.parent.rbd_volume

    @property
    def device_exists(self):
        return os.path.exists(self.device)

    @property
    def snap_exists(self):
        '''
        Plain check:  does self.device exist
        '''
        self.debugmsg("      checking existence of '%s'" %
                      self.device)
        return self.device_exists

    @property
    def orig_exists(self):
        '''
        Sanity check:  libvirt volume should be in the pool
        '''
        self.debugmsg("      checking if volume '%s' in pool '%s'" %
                      (self.virsh_volume,
                       self.libvirt_storage_pool_name))
        return self.virsh_volume in self.libvirt_storage_pool_volume_list

    @property
    def is_setup(self):
        '''
        Check if the device exists
        '''
        self.debugmsg("      checking if device '%s' exists" % self.device)
        return self.device_exists

    @property
    def is_snapshot(self):
        '''
        Sanity check: make sure at least the device isn't mounted
        anywhere outside the amanda mount_directory
        '''
        with open('/proc/mounts','r') as f:
            for line in f:
                (dev,mntpt) = line.split()[0:2]
                # This is a dumb way to check....
                if dev.startswith(self.device):
                    if not mntpt.startswith(self.params.mount_directory):
                        self.error(
                            "Target device '%s' maps to local VM device '%s' "
                            "but '%s' is already mounted on '%s'" %
                            (self.orig_device, self.device, dev, mntpt))
        # If we get here, the above check passed.
        return True

    @property
    def matches_target(self):
        '''
        Sanity check: 'device' should map back to 'orig_device' in the
        'disk' element
        '''
        # find all disk device source names for our target device
        map = [s.get('name') for s in self.libvirt_vm_xml.xpath(
                "/domain/devices/disk/target[@dev='%s']/../source" %
                self.disk_device)]
        # there should be exactly one and it should match the
        # orig_device
        return len(map) == 1 and map[0] == self.orig_device


    def wait_attach(self,detach=False):
        '''
        Check for disk attachment once a second up to the timeout
        '''
        for t in range(0,self.params.libvirt_attach_timeout):
            if detach:
                if not self.device_exists:
                    return
            else:
                if self.device_exists:
                    return
            time.sleep(1)

        self.error("Failed to attach/detach disk device '%s' "
                   "within %d seconds" %
                   (self.device, self.params.libvirt_attach_timeout))

    def create_snapshot(self):
        self.libvirt_storage_volume_attach()
        # Wait a bit for volume to be attached
        self.wait_attach()

    def remove_snapshot(self):
        self.libvirt_storage_volume_detach()
        # Wait a bit for volume to be detached
        self.wait_attach(detach=True)

    def freshen(self):
        '''
        Be sure the storage pool is updated whenever setting
        up/tearing down
        '''
        self.libvirt_storage_pool_refresh()

# Register this layer
if have_libvirt:
    Stack.register_layer(LibvirtVolLayer)
