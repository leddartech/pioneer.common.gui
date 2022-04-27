from __future__ import division

from pioneer.common import clouds, images
from pioneer.common import banks as utils
from pioneer.common.gui import Array, Product

from PyQt5.QtCore import pyqtSlot as Slot, pyqtProperty as Property, QVariant, QObject, Q_ENUMS

import numpy as np
import traceback

class CloudBase( Array.Array ):
    def __init__(self, parent = None):
        super(CloudBase, self).__init__(parent)
        self.ndarray = np.empty((0, 3), dtype = np.float32)
        #inputs:
        self._bankSelection = [] #empty means all
        self._packages = None
        self._specs = None

        #outputs:
        self._indices = Array.ArrayUInt1()
        self._indices.set_producer(self)

        self._minAmplitude = np.nan
        self._maxAmplitude = np.nan
        self._amplitudes = Array.ArrayFloat1()
        self._amplitudes.set_producer(self)

        self._banks = Array.ArrayUInt1()
        self._banks.set_producer(self)

        self._directions = None
        self._quad_directions = None

    Product.InputProperty(vars(), float, 'minAmplitude')

    Product.InputProperty(vars(), float, 'maxAmplitude')

    def _handle_specs_changed(self):
        if not self._specs:
            return
        
        self._fill_empty_specs()

        v, h, v_fov, h_fov = (self._specs[x] for x in ["v", "h", "v_fov", "h_fov"])
        if 'angles' in self._specs:
            angles = self._specs['angles']
        else:
            angles = clouds.angles(v, h, v_fov, h_fov, self.ndarray.dtype)
        print('Clouds Base specs (v,h,v_fov,h_fov): ', v, h, v_fov, h_fov)
        self._directions = clouds.directions(angles)
        self._quad_directions = clouds.quad_directions(v, h, v_fov, h_fov, self.ndarray.dtype)
        return v, h, v_fov, h_fov

    Product.InputProperty(vars(), QVariant, 'specs', _handle_specs_changed)

    Product.InputProperty(vars(), QVariant, 'bankSelection')

    Product.InputProperty(vars(), Product.VariantProduct, 'packages')

    Product.ConstProperty(vars(), Array.ArrayUInt1, 'indices')

    Product.ConstProperty(vars(), Array.ArrayFloat1, 'amplitudes')

    Product.ConstProperty(vars(), Array.ArrayUInt1, 'banks')

    def _normalize_amplitudes(self):
        min_ = self._minAmplitude if not np.isnan(self._minAmplitude) else self._amplitudes.ndarray.min()
        max_ = self._maxAmplitude if not np.isnan(self._maxAmplitude) else self._amplitudes.ndarray.max()
        self._amplitudes.ndarray = (self._amplitudes.ndarray - min_)/(max_-min_)



    def _get_package(self):
        if self._packages is None or self._packages._variant is None:
            raise RuntimeError("Could not find package")
        return self._packages._variant

    def _fill_empty_specs(self):
        if self._specs is None:
            p = self._get_package()
            self.specs =  {k:p[k] for k in ['v', 'h', 'v_fov', 'h_fov']}
        
        def other_fov(other_res, fov, res):
            camSpecs['v_fov'] = np.degrees(2 * np.arctan(other_res * np.tan(np.radians(fov)/2) / res))

        if 'v_fov' in self._specs and 'h_fov' not in self._specs:
            self._specs['h_fov'] = optics.other_fov(self._specs['h'], self._specs['v_fov'], self._specs['v'])
        elif 'h_fov' in self._specs and 'v_fov' not in self._specs:
            self._specs['v_fov'] = optics.other_fov(self._specs['v'], self._specs['h_fov'], self._specs['h'])

    def filter_banks(self):

        try:
            p =  self._get_package()
            self._fill_empty_specs()
            if self._bankSelection:

                if "ordered_to_sampled" not in self._specs or "bank_offsets" not in self._specs:
                    raise RuntimeError('Incomplete specs')

                ordered_to_sampled, bank_offsets = [self._specs[x] for x in ["ordered_to_sampled", "bank_offsets"]]
                v, h = self._specs['v'], self._specs['h']
                selections = []
                for v,h in self._bankSelection:
                    if v == -1:
                        if h == -1:
                            return p['data']
                        for v_ in range(len(bank_offsets[0])-1):
                            selections.append(utils.get_bank_indices(ordered_to_sampled, int(v_), int(h), bank_offsets[0], bank_offsets[1]))
                    elif h == -1:
                        for h_ in range(len(bank_offsets[1])-1):
                            selections.append(utils.get_bank_indices(ordered_to_sampled, int(v), int(h_), bank_offsets[0], bank_offsets[1]))                       
                    else:
                        selections.append(utils.get_bank_indices(ordered_to_sampled, int(v), int(h), bank_offsets[0], bank_offsets[1]))
                        
                bank_indices = np.concatenate(selections)
                mask = np.array(np.isin(p['data']['indices'], bank_indices))
                return p['data'][mask]

        except:
            print(traceback.format_exc())
            p = clouds.to_echo_package()
        
        return p['data']

    def clear(self):
        self.resize(0) 
        self._amplitudes.resize(0)
        self._indices.resize(0)


class ImageMode(QObject):
    DISTANCE, AMPLITUDE, MIX, FLOAT, FLIP_UD, FLIP_LR, ROT_90, ROT_90_R = [1, 2, 4, 8, 16, 32, 64, 128]

class ImageArray(CloudBase):
    def __init__(self, parent = None):
        super(ImageArray, self).__init__(parent)
        self._imageMode = ImageMode.AMPLITUDE
        self._base_shape = None

    ImageMode = ImageMode
    Q_ENUMS(ImageMode)

    def _handle_specs_changed(self):
        if self._specs is None:
            self._base_shape = None
            self.ndarray = np.empty(0)
            return

        super(ImageArray, self)._handle_specs_changed()

        c = 0
        if self._imageMode & ImageMode.DISTANCE:
            c += 1
        if self._imageMode & ImageMode.AMPLITUDE:
            c += 1
        if self._imageMode & ImageMode.MIX:
            c += 1

        self._base_shape = (self._specs['v'],self._specs['h'],c) if c > 1 else (self._specs['v'],self._specs['h'])

        self.ndarray = np.zeros(self._base_shape, dtype = np.float32 if (self._imageMode & ImageMode.FLOAT) else np.uint8)

    Product.InputProperty(vars(), int, 'imageMode', _handle_specs_changed)






    def _update(self):

        self.clear()

        try:
            data  = self.filter_banks()
        except:
            return
        if data.size == 0:
            return

        if self._bankSelection:
            print('Bank selection is an untested feature for image arrays')

        amp, other_rv = images.extrema_image(self._specs['v'], self._specs['h']
                                          , data
                                          , sort_field='amplitudes'
                                          , dtype = np.float32
                                          , other_fields=['distances'])

        dst = other_rv['distances']

        a = np.zeros(self._base_shape, np.float32, order='C')
        if len(a.shape) == 2:
            a = np.expand_dims(a, axis=-1)

        c = 0
        if self._imageMode & ImageMode.DISTANCE:
            a[:,:,c] = dst
            c += 1
        if self._imageMode & ImageMode.AMPLITUDE:
            a[:,:,c] = amp
            c += 1
        if self._imageMode & ImageMode.MIX:
            a[:,:,c] = dst * amp
            c += 1

        if len(self._base_shape) == 2:
            a = a[:,:,0]

        if self._imageMode & ImageMode.FLIP_UD:
            a = np.flipud(a)
        if self._imageMode & ImageMode.FLIP_LR:
            a = np.fliplr(a)
        if self._imageMode & ImageMode.ROT_90:
            a = np.rot90(a)
        if self._imageMode & ImageMode.ROT_90_R:
            a = np.rot90(a, k=-1)

        # Remember to flip image in both x  to align pixel progression with standard screen coordinates
        # (x is left-to-right, y is top to bottom, z is into the screen), we don't do it here to be able to map a pixel to a channel number
        if self._imageMode & ImageMode.FLOAT:
            self.ndarray = np.copy(a)
        else:
            self.ndarray = (a*255).astype(np.uint8)



class PointCloud( CloudBase ):
    def __init__(self, parent = None):
        super(PointCloud, self).__init__(parent)

    def _update(self):
        
        self.clear()

        try:
            #FIXME: horrible hack to use das stuff from leddar_gui
            p =  self._get_package()
            sample = p['das.sample']
            self.ndarray = sample.get_point_cloud(referential = None, ignore_orientation=True)
            self.indices.ndarray = np.arange(self.ndarray.shape[0], dtype=np.uint32)
            return
        except:
            pass

        data  = self.filter_banks()

        if data.size == 0:
            return

        self.ndarray = clouds.to_point_cloud(data['indices']
                                           , data['distances']
                                           , self._directions
                                           , self.ndarray.dtype)
        self._amplitudes.ndarray = data['amplitudes'][:, np.newaxis]
        self.indices.ndarray = np.arange(self.ndarray.shape[0], dtype=np.uint32)
        self._normalize_amplitudes()

class SurfaceCloud( CloudBase ):
    def __init__(self, parent = None):
        super(SurfaceCloud, self).__init__(parent)

    def _triangle_at(self, n):
        return self._indices.ndarray[n * 3 : n * 3 + 3]

    @Slot(int, result = int)
    def channel(self, n):
        triangle = self._triangle_at(n)
        data  = self.filter_banks()

        return data['indices'][clouds.triangle_to_echo_index(triangle)]

    @Slot(int, result = QVariant)
    def channelInfo(self, n):
        triangle = self._triangle_at(n)
        echo_i = clouds.triangle_to_echo_index(triangle)
        data  = self.filter_banks()

        channel_i = data['indices'][echo_i]

        h = self._specs['h']
        try:
            coeff = self._get_package()['timestamps_to_us_coeff']
        except:
            coeff = 1
        rv = {'v': int(channel_i//h), 'h': int(channel_i%h)
                         , 'distance': float(data['distances'][echo_i])
                         , 'amplitude': float(data['amplitudes'][echo_i])
                         , 'timestamp': int(data['timestamps'][echo_i] * coeff)
                         , 'flag': int(data['flags'][echo_i])}

        return QVariant(rv)

    def _update(self):

        self.clear()



        data  = self.filter_banks()

        if data.size == 0:
            return

        
        self.ndarray, self._amplitudes.ndarray, self._indices.ndarray = clouds.to_quad_cloud(data['indices']
                                   , data['distances']
                                   , data['amplitudes']
                                   , self._quad_directions
                                   , self._specs['v']
                                   , self._specs['h']
                                   , dtype = np.float32)

        self._normalize_amplitudes()


class SensorReferential( CloudBase ):
    def __init__(self, parent = None):
        '''
        It may appears bit deceiving that this class derive from CloudBase,
        but this way we ensure we use 'quad_directions' as computed for 3d projection,
        therefore keeping referential naturally in sync with projection model
        '''
        super(SensorReferential, self).__init__(parent)
        self._depth = 5
        ## 0,5, 0,6, 0,7, 0,8 mid-lines
        self._indices.ndarray = np.array([ 0,1 , 0,2 , 0,3 , 0,4 , 1,2 , 2,4 , 4,3, 3,1], dtype="uint32")


    Product.InputProperty(vars(), float, 'depth')


    def _update(self):
        
        self._fill_empty_specs()

        self.ndarray.resize((9,3))

        v, h = [self._specs[x] for x in ["v", "h"]]
        mid_v, mid_h = (v+1)//2, (h+1)//2
        n = v * h

        def index(v_i, h_i, offset):
            return v_i * h + h_i + offset

        self.ndarray[0] = [0,0,0]
        self.ndarray[1:] = self._quad_directions[[index(0,0,0), index(0,h-1,3*n), index(v-1, 0, n), index(v-1, h-1, 2*n)
                                                          , index(0, mid_h,0), index(v-1,mid_h,0), index(mid_v,0,0), index(mid_v, h-1,0)]] * self._depth


