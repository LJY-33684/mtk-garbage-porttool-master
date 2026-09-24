from os import getcwd
import os.path as op
from . import archdetect

import json

# configs for porttool
support_chipset_portstep = {
    'mt6572/mt6582/mt6592 kernel-3.4.67': {
        'partitions': {
            'system': '/dev/block/mmcblk0p4',
            'boot': '/dev/block/bootimg'
        },
        'flags': {
            'generate_script': True,
            'replace_kernel': True,
            'replace_fstab': False,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True,
            'replace_malidriver': True,
            'replace_audiodriver': True,
            'replace_libshowlogo': False,
            'replace_mtk-kpd': True,
            'replace_gralloc': True,
            'replace_hwcomposer': True,
            'replace_ril': False,
            'replace_sensors': False,
            'replace_gps': False,
            'replace_power': False,
            'replace_bluetooth': False,
            'replace_vibrator': False,
            'replace_thermal': False,
            'single_simcard': False,
            'dual_simcard': False,
            'fit_density': True,
            'change_model': True,
            'change_timezone': True,
            'change_locale': True,
            'use_custom_update-binary': True
        },
        'replace': {
            'kernel': [
                'kernel'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt6572',
                'initrd/fstab.mt6582',
                'initrd/fstab.mt6592'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ],
            'malidriver': [
                'lib/libMali.so',
                'vendor/lib/libMali.so',
                'vendor/lib/egl',
                'vendor/lib/hw/vulkan.*',
                'vendor/lib/libIMGegl.so',
                'vendor/lib/libpvrANDROID_WSEGL.so',
                'vendor/lib/libgpu_aux.so'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'vendor/lib/libshowlogo.so'
            ],
            'mtk-kpd': [
                'usr/keylayout/mtk-kpd.kl'
            ],
            'ril': [
                'bin/ccci_fsd',
                'bin/ccci_mdinit',
                'bin/gsm0710muxd',
                'bin/gsm0710muxdmd2',
                'bin/rild',
                'bin/rildmd2',
                'vendor/bin/ccci_fsd',
                'vendor/bin/ccci_mdinit',
                'vendor/bin/gsm0710muxd',
                'vendor/bin/rild',
                'vendor/bin/mtkfusionrild',
                'lib/librilmtk.so',
                'lib/librilmtkmd2.so',
                'lib/librilutils.so',
                'lib/mtk-ril.so',
                'lib/mtk-rilmd2.so',
                'vendor/lib/librilmtk.so',
                'vendor/lib/libmtk-ril.so',
                'vendor/lib/librilfusion.so',
                'vendor/lib/librilutilsmtk.so',
                'vendor/lib/libccci_util.so'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'vendor/lib/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*'
            ],
            'thermal': [
                'vendor/etc/.tp'
            ]
        }
    },
    'auto (同平台通用)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'replace_kernel': True,
            'replace_fstab': False,
            'selinux_permissive': True,
            'enable_adb': True,
            'auto_replace': True,
            'replace_firmware': False,
            'replace_mddb': False,
            'replace_malidriver': False,
            'replace_audiodriver': False,
            'replace_libshowlogo': False,
            'replace_mtk-kpd': False,
            'replace_gralloc': False,
            'replace_hwcomposer': False,
            'replace_ril': False,
            'replace_sensors': False,
            'replace_gps': False,
            'replace_power': False,
            'replace_bluetooth': False,
            'replace_vibrator': False,
            'replace_thermal': False,
            'replace_wifi': False,
            'replace_camera': False,
            'single_simcard': False,
            'dual_simcard': False,
            'fit_density': True,
            'change_model': True,
            'change_timezone': True,
            'change_locale': True,
            'use_custom_update-binary': True
        },
        'replace': {
            'kernel': [
                'kernel',
                'kernel.gz'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt6735',
                'initrd/fstab.mt6737'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ],
            'malidriver': [
                'lib/libMali.so',
                'vendor/lib/libMali.so',
                'vendor/lib/egl',
                'vendor/lib/hw/vulkan.*',
                'vendor/lib/libIMGegl.so',
                'vendor/lib/libpvrANDROID_WSEGL.so',
                'vendor/lib/libgpu_aux.so'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'etc/audio_policy.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'vendor/lib/libshowlogo.so'
            ],
            'mtk-kpd': [
                'usr/keylayout/mtk-kpd.kl'
            ],
            'ril': [
                'bin/ccci_fsd',
                'bin/ccci_mdinit',
                'bin/gsm0710muxd',
                'bin/rild',
                'vendor/bin/ccci_fsd',
                'vendor/bin/ccci_mdinit',
                'vendor/bin/gsm0710muxd',
                'vendor/bin/rild',
                'vendor/bin/mtkfusionrild',
                'lib/librilmtk.so',
                'lib/librilutils.so',
                'lib/mtk-ril.so',
                'vendor/lib/librilmtk.so',
                'vendor/lib/libmtk-ril.so',
                'vendor/lib/librilfusion.so',
                'vendor/lib/librilutilsmtk.so',
                'vendor/lib/libccci_util.so'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'vendor/lib/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*'
            ],
            'thermal': [
                'vendor/etc/.tp'
            ],
            'wifi': [
                'bin/netcfg',
                'bin/dhcpcd',
                'bin/ifconfig',
                'bin/hostap',
                'bin/hostapd',
                'bin/hostapd_bin',
                'bin/pcscd',
                'bin/wlan*',
                'bin/wpa*',
                'bin/netd',
                'lib/libhardware_legacy.so',
                'lib/libwpa_client.so',
                'lib/libwifi-service.so',
                'etc/wifi',
                'vendor/firmware',
                'vendor/bin/netdiag',
                'vendor/lib/libem_wifi_jni.so'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib/lib3a.so',
                'lib/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib/libimageio.so',
                'lib/libimageio_plat_drv.so',
                'lib/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib/libmhalImageCodec.so',
                'lib/libmtkcamera_client.so',
                'lib/libmtkjpeg.so',
                'lib/libcam.paramsmgr.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib/lib3a.so',
                'vendor/lib/libcamalgo.so',
                'vendor/lib/libcamdrv.so',
                'vendor/lib/libcameracustom.so',
                'vendor/lib/libfeatureio.so',
                'vendor/lib/libimageio.so',
                'vendor/lib/libimageio_plat_drv.so',
                'vendor/lib/libJpgDecPipe.so',
                'vendor/lib/libJpgEncPipe.so',
                'vendor/lib/libmhalImageCodec.so',
                'vendor/lib/libmtkcamera_client.so',
                'vendor/lib/libmtkjpeg.so',
                'vendor/lib/libcam.paramsmgr.so',
                'vendor/lib/libcam.camadapter.so',
                'vendor/lib/libcam.camnode.so',
                'vendor/lib/libcam.camshot.so',
                'vendor/lib/libcam.client.so',
                'vendor/lib/libcam.device1.so',
                'vendor/lib/libcam.device3.so',
                'vendor/lib/libcam.exif.so',
                'vendor/lib/libcam.hal3a.v3.so',
                'vendor/lib/libcam.halsensor.so',
                'vendor/lib/libcam.iopipe.so',
                'vendor/lib/libcam.metadataprovider.so',
                'vendor/lib/libcam.utils.so',
                'vendor/lib/libcam_utils.so',
                'vendor/lib/libfeatureiodrv.so',
                'vendor/lib/libSwJpgCodec.so'
            ]
        }
    },
    'kernel only (only replace kernel)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'kernel_only_mode': True,
            'replace_kernel': True,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True
        },
        'replace': {
            'kernel': [
                'kernel',
                'kernel.gz'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ]
        }
    },
    'G79 (mt6735/mt6735m/mt6737) kernel-3.18.19': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'replace_kernel': True,
            'replace_fstab': False,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True,
            'replace_malidriver': False,
            'replace_audiodriver': True,
            'replace_libshowlogo': False,
            'replace_mtk-kpd': False,
            'replace_gralloc': True,
            'replace_hwcomposer': True,
            'replace_ril': False,
            'replace_sensors': False,
            'replace_gps': False,
            'replace_power': False,
            'replace_bluetooth': False,
            'replace_vibrator': False,
            'replace_thermal': False,
            'replace_wifi': False,
            'replace_camera': False,
            'single_simcard': False,
            'dual_simcard': False,
            'fit_density': True,
            'change_model': True,
            'change_timezone': True,
            'change_locale': True,
            'use_custom_update-binary': True
        },
        'replace': {
            'kernel': [
                'kernel'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt6735',
                'initrd/fstab.mt6737'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ],
            'malidriver': [
                'lib/libMali.so',
                'vendor/lib/libMali.so',
                'vendor/lib/egl',
                'vendor/lib/hw/vulkan.*',
                'vendor/lib/libIMGegl.so',
                'vendor/lib/libpvrANDROID_WSEGL.so',
                'vendor/lib/libgpu_aux.so'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'etc/audio_policy.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'vendor/lib/libshowlogo.so'
            ],
            'mtk-kpd': [
                'usr/keylayout/mtk-kpd.kl'
            ],
            'ril': [
                'bin/ccci_fsd',
                'bin/ccci_mdinit',
                'bin/gsm0710muxd',
                'bin/rild',
                'vendor/bin/ccci_fsd',
                'vendor/bin/ccci_mdinit',
                'vendor/bin/gsm0710muxd',
                'vendor/bin/rild',
                'vendor/bin/mtkfusionrild',
                'lib/librilmtk.so',
                'lib/librilutils.so',
                'lib/mtk-ril.so',
                'vendor/lib/librilmtk.so',
                'vendor/lib/libmtk-ril.so',
                'vendor/lib/librilfusion.so',
                'vendor/lib/librilutilsmtk.so',
                'vendor/lib/libccci_util.so'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'vendor/lib/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*'
            ],
            'thermal': [
                'vendor/etc/.tp'
            ],
            'wifi': [
                'bin/netcfg',
                'bin/dhcpcd',
                'bin/ifconfig',
                'bin/hostap',
                'bin/hostapd',
                'bin/hostapd_bin',
                'bin/pcscd',
                'bin/wlan*',
                'bin/wpa*',
                'bin/netd',
                'lib/libhardware_legacy.so',
                'lib/libwpa_client.so',
                'lib/libwifi-service.so',
                'etc/wifi',
                'vendor/firmware',
                'vendor/bin/netdiag',
                'vendor/lib/libem_wifi_jni.so'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib/lib3a.so',
                'lib/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib/libimageio.so',
                'lib/libimageio_plat_drv.so',
                'lib/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib/libmhalImageCodec.so',
                'lib/libmtkcamera_client.so',
                'lib/libmtkjpeg.so',
                'lib/libcam.paramsmgr.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib/lib3a.so',
                'vendor/lib/libcamalgo.so',
                'vendor/lib/libcamdrv.so',
                'vendor/lib/libcameracustom.so',
                'vendor/lib/libfeatureio.so',
                'vendor/lib/libimageio.so',
                'vendor/lib/libimageio_plat_drv.so',
                'vendor/lib/libJpgDecPipe.so',
                'vendor/lib/libJpgEncPipe.so',
                'vendor/lib/libmhalImageCodec.so',
                'vendor/lib/libmtkcamera_client.so',
                'vendor/lib/libmtkjpeg.so',
                'vendor/lib/libcam.paramsmgr.so',
                'vendor/lib/libcam.camadapter.so',
                'vendor/lib/libcam.camnode.so',
                'vendor/lib/libcam.camshot.so',
                'vendor/lib/libcam.client.so',
                'vendor/lib/libcam.device1.so',
                'vendor/lib/libcam.device3.so',
                'vendor/lib/libcam.exif.so',
                'vendor/lib/libcam.hal3a.v3.so',
                'vendor/lib/libcam.halsensor.so',
                'vendor/lib/libcam.iopipe.so',
                'vendor/lib/libcam.metadataprovider.so',
                'vendor/lib/libcam.utils.so',
                'vendor/lib/libcam_utils.so',
                'vendor/lib/libfeatureiodrv.so',
                'vendor/lib/libSwJpgCodec.so'
            ]
        }
    },
    'mt6580/mt8321 (通用, Android 5.1-7.1.2)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'replace_kernel': True,
            'replace_fstab': False,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True,
            'replace_malidriver': True,
            'replace_audiodriver': True,
            'replace_libshowlogo': False,
            'replace_mtk-kpd': False,
            'replace_gralloc': True,
            'replace_hwcomposer': True,
            'replace_ril': False,
            'replace_sensors': False,
            'replace_gps': False,
            'replace_power': False,
            'replace_bluetooth': False,
            'replace_vibrator': False,
            'replace_thermal': False,
            'single_simcard': False,
            'dual_simcard': False,
            'fit_density': True,
            'change_model': True,
            'change_timezone': True,
            'change_locale': True,
            'use_custom_update-binary': True
        },
        'replace': {
            'kernel': [
                'kernel'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt6580'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ],
            'malidriver': [
                'lib/libMali.so',
                'vendor/lib/libMali.so',
                'vendor/lib/egl',
                'vendor/lib/hw/vulkan.*',
                'vendor/lib/libIMGegl.so',
                'vendor/lib/libpvrANDROID_WSEGL.so',
                'vendor/lib/libgpu_aux.so'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'vendor/lib/libshowlogo.so'
            ],
            'mtk-kpd': [
                'usr/keylayout/mtk-kpd.kl'
            ],
            'ril': [
                'bin/ccci_fsd',
                'bin/ccci_mdinit',
                'bin/gsm0710muxd',
                'bin/rild',
                'vendor/bin/mtkfusionrild',
                'lib/librilmtk.so',
                'lib/librilutils.so',
                'lib/mtk-ril.so',
                'vendor/lib/libccci_util.so'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'vendor/lib/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*'
            ],
            'thermal': [
                'vendor/etc/.tp'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib/lib3a.so',
                'lib/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib/libimageio.so',
                'lib/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib/libmtkjpeg.so',
                'vendor/lib/hw/camera.*'
            ]
        }
    },
    'mt8163/mt8127/mt8167 (平板, Android 5.1-7.1.2)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'replace_kernel': True,
            'replace_fstab': False,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True,
            'replace_malidriver': True,
            'replace_audiodriver': True,
            'replace_libshowlogo': False,
            'replace_mtk-kpd': False,
            'replace_gralloc': True,
            'replace_hwcomposer': True,
            'replace_ril': False,
            'replace_sensors': False,
            'replace_gps': False,
            'replace_power': False,
            'replace_bluetooth': False,
            'replace_vibrator': False,
            'replace_thermal': False,
            'replace_wifi': True,
            'replace_camera': True,
            'single_simcard': False,
            'dual_simcard': False,
            'fit_density': True,
            'change_model': True,
            'change_timezone': True,
            'change_locale': True,
            'use_custom_update-binary': True
        },
        'replace': {
            'kernel': [
                'kernel'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt8163',
                'initrd/fstab.mt8127',
                'initrd/fstab.mt8167'
            ],
            'firmware': [
                'etc/firmware',
                'vendor/firmware'
            ],
            'mddb': [
                'etc/mddb',
                'vendor/etc/mddb'
            ],
            'malidriver': [
                'lib/libMali.so',
                'vendor/lib/libMali.so',
                'vendor/lib/egl',
                'lib/egl',
                'vendor/lib/hw/vulkan.*'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'vendor/lib/libshowlogo.so'
            ],
            'mtk-kpd': [
                'usr/keylayout/mtk-kpd.kl'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib/hw/lights.*'
            ],
            'power': [
                'lib/hw/power.*',
                'vendor/lib/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib/libbt-vendor.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*'
            ],
            'thermal': [
                'vendor/etc/.tp'
            ],
            'wifi': [
                'etc/wifi',
                'vendor/etc/wifi',
                'vendor/firmware'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib/lib3a.so',
                'lib/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib/libimageio.so',
                'lib/libmtkjpeg.so',
                'vendor/lib/hw/camera.*'
            ]
        }
    }
}

if op.isfile("configs.json"):
    with open("configs.json", 'r') as c:
        support_chipset_portstep = json.load(c)
else:
    with open("configs.json", 'w') as c:
        json.dump(support_chipset_portstep, c, indent=4)

support_chipset = list(support_chipset_portstep.keys())
support_packtype = ['zip', 'img']
ostype, arch = archdetect.retTypeAndMachine()
ext_ext = '.exe' if ostype == 'win' else ''

# binarys
make_ext4fs_bin = op.join(getcwd(), "bin", ostype, arch, "make_ext4fs"+ext_ext)
magiskboot_bin = op.join(getcwd(), "bin", ostype, arch, "magiskboot"+ext_ext)
simg2img_bin = op.join(getcwd(), "bin", ostype, arch, "simg2img"+ext_ext)
img2simg_bin = op.join(getcwd(), "bin", ostype, arch, "img2simg"+ext_ext)
