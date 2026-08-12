# Dependencies: matplotlib package
import asyncio
import csv

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger
import time as t
import matplotlib.pyplot as plt

from horiba_sdk.core.acquisition_format import AcquisitionFormat
from horiba_sdk.core.timer_resolution import TimerResolution
from horiba_sdk.core.x_axis_conversion_type import XAxisConversionType
from horiba_sdk.devices.device_manager import DeviceManager
from horiba_sdk.devices.single_devices.monochromator import Monochromator

async def wait_for_ccd(ccd):
    acquisition_busy = True
    while acquisition_busy:
        acquisition_busy = await ccd.get_acquisition_busy()
        await asyncio.sleep(0.1)
        logger.info('Acquisition busy')


async def wait_for_mono(mono):
    mono_busy = True
    while mono_busy:
        mono_busy = await mono.is_busy()
        await asyncio.sleep(0.1)
        logger.info('Mono busy...')

async def connect_devices():        
    device_manager = DeviceManager(start_icl=True)
    await device_manager.start()
    
    if not device_manager.charge_coupled_devices or not device_manager.monochromators:
        logger.error('Required monochromator or ccd not found')
        await device_manager.stop()
        return

    mono = device_manager.monochromators[0]
    await mono.open()
    await wait_for_mono(mono)
    
    ccd = device_manager.charge_coupled_devices[1] # 0 symphony, 1 syncerity
    await ccd.open()
    await wait_for_ccd(ccd)
    
    return mono,ccd,device_manager

async def set_mono_wavelength(mono,ccd,centerWavelength):
    await mono.move_to_target_wavelength(centerWavelength)
    await wait_for_mono(mono)
    mono_wavelength = await mono.get_current_wavelength()
    logger.info(f'Mono wavelength {mono_wavelength}')
    await ccd.set_center_wavelength(mono.id(), mono_wavelength)
    await ccd.set_x_axis_conversion_type(XAxisConversionType.FROM_ICL_SETTINGS_INI)

    
async def set_slit_width(mono,slitWidth):
    """
    slit width in mm
    """
    await mono.set_slit_position(mono.Slit.A, slitWidth)
    
async def configure_mono(mono,initialize = False):
    if initialize:
        await mono.initialize()
    await wait_for_mono(mono)
    await mono.set_turret_grating(Monochromator.Grating.SECOND)
    #await mono.set_turret_grating(Monochromator.Grating.THIRD)
    await wait_for_mono(mono)
    await mono.set_mirror_position(mono.Mirror.EXIT, mono.MirrorPosition.AXIAL)
    #await mono.set_mirror_position(mono.Mirror.EXIT, mono.MirrorPosition.LATERAL)
    await wait_for_mono(mono)
    
async def configure_ccd(ccd, mono, gainToken = 2, speedToken = 0, acquisition_count=1):
    ccd_config = await ccd.get_configuration()
    print(ccd_config)
    chip_x = int(ccd_config['chipWidth'])
    chip_y = int(ccd_config['chipHeight'])
    await ccd.set_acquisition_count(acquisition_count)    
    center_wavelength =  await mono.get_current_wavelength()
    await ccd.set_center_wavelength(mono.id(), center_wavelength)
    await ccd.set_x_axis_conversion_type(XAxisConversionType.FROM_ICL_SETTINGS_INI)
    
    
    await ccd.set_gain(gainToken)  # 0: high light, 1: Best dynamic range, 2: high gain
    await ccd.set_speed(speedToken)  # 0: 45kHz , 1: 1 Mhz, 2: 1 MHz Ultra
    await ccd.set_timer_resolution(TimerResolution.MILLISECONDS)
    await ccd.set_acquisition_format(1, AcquisitionFormat.SPECTRA)
    
async def set_exposure_time(ccd,exposureTime):
    await ccd.set_exposure_time(exposureTime)
    
async def set_roi(ccd, x_origin=0, x_size = 1024, x_bin=1, y_origin = 80, y_size = 100, y_bin=100):
    await ccd.set_region_of_interest(x_origin=x_origin,x_size = x_size, x_bin= x_bin, y_origin = y_origin, y_size = y_size, y_bin= y_bin)
    
async def reset_ccd(ccd):
    while await ccd.get_acquisition_busy():
        # CCD will be busy infinitely because it is waiting for a trigger that is not coming.
        # That's why the abort command needs to be sent.
        await asyncio.sleep(0.3)
        await ccd.acquisition_abort()
  
    # restart the CCD to reset the trigger
    await ccd.restart()
    await asyncio.sleep(7)
  
async def get_spectrum(ccd,exposureTime):
    """
    exposure time in seconds

    """
    if await ccd.get_acquisition_ready():
        await ccd.acquisition_start(open_shutter=True)
        await asyncio.sleep(exposureTime+0.005)  # While the acquisition happens, we can yield the processor
        # Poll for acquisition status
        acquisition_busy = True
        while acquisition_busy:
            acquisition_busy = await ccd.get_acquisition_busy()
            await asyncio.sleep(0.002)  # Acquisition should be done, so we can poll pretty fast
            #logger.info('Acquisition busy')

        raw_data = await ccd.get_acquisition_data()
        x_data = raw_data[0]['roi'][0]['xData']
        y_data = raw_data[0]['roi'][0]['yData']
        return x_data, y_data[0]
    
    else:
        raise Exception('CCD not ready for acquisition')