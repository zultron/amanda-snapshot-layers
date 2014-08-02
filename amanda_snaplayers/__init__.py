# Import (and automatically register) the various supported layers
from layer_xenvdi import XenVDISnapLayer
from layer_md import MD_component_device
from layer_mount_partition import MountPartition
from layer_lv import LV
from layer_rbd import RBDSnapLayer
from layer_libvirt import LibvirtVolLayer

# Calling scripts use these
from params import Params
from stack import Stack
