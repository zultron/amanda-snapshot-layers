# The Stack class

from util import Util

class Stack(Util):

    dispatch_hash = {}

    @classmethod
    def register_layer(my_class,layer_class):
        my_class.dispatch_hash[layer_class.name] = layer_class

    def insert_layer(self,name,args):
        # Look up layer class
        layer_class = self.dispatch_hash.get(name,None)
        if layer_class is None:
            self.error("Unrecognized layer name '%s'" % name)

        # Insert parent layers, if applicable
        if hasattr(layer_class, 'insert_parent'):
            self.insert_layer(layer_class.insert_parent, args)

        # Determine parent layer
        if self.layers:
            parent_layer = self.layers[-1]
        else:
            parent_layer = None

        # Instantiate layer and put on stack
        layer = layer_class(args, self.params, parent_layer)
        self.layers.append(layer)

        # Print info
        layer.print_info()
        self.infomsg('')


    def __init__(self,params,debug=None):
        # set up utils; we expect logging to already be set up from 'params'
        super(Stack, self).__init__(debug=params.debug)
        if debug is not None:
            self.debug = debug

        self.params = params

        # after a check(), these will be True or False
        self.is_setup = None
        self.is_stale = None

        # after a check(), this will be the top layer found to be set up
        self.top_set_up_layer = None

        # build layer stack
        self.layers = []
        for layer in params.scheme:
            (layer_name,layer_args) = (layer+[None])[0:2]
            self.insert_layer(layer_name, layer_args)

        # if top isn't a Mount object, add one, assuming an unpartitioned
        # block device with a mountable filesystem
        if not isinstance(self.layers[-1], Mount):
            self.layers.append(Mount('0', self.params, parent_layer))
            self.layers[-1].print_info()
            self.infomsg('')

    def check(self):
        self.is_stale = False
        self.is_setup = True
        for layer in self.layers:
            self.debugmsg("Checking layer '%s', args '%s'" %
                          (layer.name, layer.arg_str))
            if layer.is_setup:
                self.top_set_up_layer = layer
                if layer.is_stale:
                    self.debugmsg("Layer '%s' set up but stale\n" %
                                  layer.name)
                    self.is_stale = True
                else:
                    self.debugmsg("Layer '%s' set up and not stale\n" %
                                  layer.name)
            else:
                self.is_setup = False
                self.debugmsg("Layer '%s' not set up; end of check\n" %
                              layer.name)
                # don't continue; uninitialized lower layers aren't required
                # to provide a parent device for higher layers
                break

    @property
    def is_torn_down(self):
        if self.is_setup is None:
            self.check()
        return self.top_set_up_layer is None

    def tear_down(self):
        if self.is_setup is None:
            self.error("Stack tear_down() method called before "
                       "check(); aborting")
        while self.top_set_up_layer is not None:
            layer = self.top_set_up_layer
            self.top_set_up_layer = layer.parent
            layer.safe_teardown()

    def set_up(self):
        if self.is_setup is None:
            self.error("Stack set_up() method called before "
                       "check(); aborting")
        for layer in self.layers:
            layer.safe_set_up()


class Mount(object):
    '''
    A Mount class object mounts a filesystem
    '''

    pass
