import os.path as op
from . import archdetect

# 仓库根目录（基于本文件定位，避免依赖当前工作目录；configs.py 位于 <根>/porttool/ 下）
_ROOT = op.dirname(op.dirname(op.abspath(__file__)))

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
            'replace_wifi': False,
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
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'lib64/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib64/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib64/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib64/libksensor.so',
                'vendor/lib/librgbwlightsensor.so',
                'vendor/lib64/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'lib64/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/lib64/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so',
                'vendor/lib64/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'lib64/hw/power.*',
                'vendor/lib/hw/power.*',
                'vendor/lib64/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'lib64/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib64/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib64/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib64/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'vendor/lib64/libbluetooth_relayer.so',
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
                'bin/wpa_supplicant',
                'bin/hostapd',
                'bin/wpa_cli',
                'etc/wifi',
                'lib/libwpa_client.so',
                'lib/libwifi-service.so'
            ],        }
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
            'replace_audioengine': True,
            'replace_tfa': True,
            'replace_init': False,
            'change_platform': False,
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
            'init': [
                'initrd/init.mt6735.rc',
                'initrd/init.mt6737.rc',
                'initrd/init.mt6735.usb.rc',
                'initrd/init.project.rc'
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
                'lib64/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'vendor/lib64/hw/audio.primary.*',
                'lib/hw/audio_policy.default.so',
                'lib64/hw/audio_policy.default.so',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'etc/audio_policy.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'audioengine': [
                'lib/libaudiocomp*',
                'lib64/libaudiocomp*',
                'vendor/lib/libaudiocomp*',
                'vendor/lib64/libaudiocomp*',
                'lib/libaudioroute*',
                'lib64/libaudioroute*',
                'vendor/lib/libaudioroute*',
                'vendor/lib64/libaudioroute*',
                'lib/libaudioparam*',
                'lib64/libaudioparam*',
                'vendor/lib/libaudioparam*',
                'vendor/lib64/libaudioparam*'
            ],
            'tfa': [
                'etc/tfa*',
                'lib/libtfa*',
                'lib64/libtfa*',
                'vendor/lib/libtfa*',
                'vendor/lib64/libtfa*',
                'lib/libaudiotfa*',
                'lib64/libaudiotfa*'
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
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'lib64/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib64/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib64/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib64/libksensor.so',
                'vendor/lib/librgbwlightsensor.so',
                'vendor/lib64/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'lib64/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/lib64/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so',
                'vendor/lib64/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'lib64/hw/power.*',
                'vendor/lib/hw/power.*',
                'vendor/lib64/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'lib64/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib64/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib64/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib64/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'vendor/lib64/libbluetooth_relayer.so',
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
                'lib64/libhardware_legacy.so',
                'lib/libwpa_client.so',
                'lib64/libwpa_client.so',
                'lib/libwifi-service.so',
                'lib64/libwifi-service.so',
                'etc/wifi',
                'vendor/firmware',
                'vendor/bin/netdiag',
                'vendor/lib/libem_wifi_jni.so',
                'vendor/lib64/libem_wifi_jni.so'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib64/hw/camera.*',
                'lib/lib3a.so',
                'lib64/lib3a.so',
                'lib/libcamalgo.so',
                'lib64/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib64/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib64/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib64/libfeatureio.so',
                'lib/libimageio.so',
                'lib64/libimageio.so',
                'lib/libimageio_plat_drv.so',
                'lib64/libimageio_plat_drv.so',
                'lib/libJpgDecPipe.so',
                'lib64/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib64/libJpgEncPipe.so',
                'lib/libmhalImageCodec.so',
                'lib64/libmhalImageCodec.so',
                'lib/libmtkcamera_client.so',
                'lib64/libmtkcamera_client.so',
                'lib/libmtkjpeg.so',
                'lib64/libmtkjpeg.so',
                'lib/libcam.paramsmgr.so',
                'lib64/libcam.paramsmgr.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib64/hw/camera.*',
                'vendor/lib/lib3a.so',
                'vendor/lib64/lib3a.so',
                'vendor/lib/libcamalgo.so',
                'vendor/lib64/libcamalgo.so',
                'vendor/lib/libcamdrv.so',
                'vendor/lib64/libcamdrv.so',
                'vendor/lib/libcameracustom.so',
                'vendor/lib64/libcameracustom.so',
                'vendor/lib/libfeatureio.so',
                'vendor/lib64/libfeatureio.so',
                'vendor/lib/libimageio.so',
                'vendor/lib64/libimageio.so',
                'vendor/lib/libimageio_plat_drv.so',
                'vendor/lib64/libimageio_plat_drv.so',
                'vendor/lib/libJpgDecPipe.so',
                'vendor/lib64/libJpgDecPipe.so',
                'vendor/lib/libJpgEncPipe.so',
                'vendor/lib64/libJpgEncPipe.so',
                'vendor/lib/libmhalImageCodec.so',
                'vendor/lib64/libmhalImageCodec.so',
                'vendor/lib/libmtkcamera_client.so',
                'vendor/lib64/libmtkcamera_client.so',
                'vendor/lib/libmtkjpeg.so',
                'vendor/lib64/libmtkjpeg.so',
                'vendor/lib/libcam.paramsmgr.so',
                'vendor/lib64/libcam.paramsmgr.so',
                'vendor/lib/libcam.camadapter.so',
                'vendor/lib64/libcam.camadapter.so',
                'vendor/lib/libcam.camnode.so',
                'vendor/lib64/libcam.camnode.so',
                'vendor/lib/libcam.camshot.so',
                'vendor/lib64/libcam.camshot.so',
                'vendor/lib/libcam.client.so',
                'vendor/lib64/libcam.client.so',
                'vendor/lib/libcam.device1.so',
                'vendor/lib64/libcam.device1.so',
                'vendor/lib/libcam.device3.so',
                'vendor/lib64/libcam.device3.so',
                'vendor/lib/libcam.exif.so',
                'vendor/lib64/libcam.exif.so',
                'vendor/lib/libcam.hal3a.v3.so',
                'vendor/lib64/libcam.hal3a.v3.so',
                'vendor/lib/libcam.halsensor.so',
                'vendor/lib64/libcam.halsensor.so',
                'vendor/lib/libcam.iopipe.so',
                'vendor/lib64/libcam.iopipe.so',
                'vendor/lib/libcam.metadataprovider.so',
                'vendor/lib64/libcam.metadataprovider.so',
                'vendor/lib/libcam.utils.so',
                'vendor/lib64/libcam.utils.so',
                'vendor/lib/libcam_utils.so',
                'vendor/lib64/libcam_utils.so',
                'vendor/lib/libfeatureiodrv.so',
                'vendor/lib64/libfeatureiodrv.so',
                'vendor/lib/libSwJpgCodec.so',
                'vendor/lib64/libSwJpgCodec.so'
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
            'replace_wifi': False,
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
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'lib64/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib64/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib64/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib64/libksensor.so',
                'vendor/lib/librgbwlightsensor.so',
                'vendor/lib64/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'lib64/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/lib64/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so',
                'vendor/lib64/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'lib64/hw/power.*',
                'vendor/lib/hw/power.*',
                'vendor/lib64/hw/power.*'
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
            ],
            'wifi': [
                'bin/wpa_supplicant',
                'bin/hostapd',
                'bin/wpa_cli',
                'etc/wifi',
                'lib/libwpa_client.so',
                'lib/libwifi-service.so'
            ],        }
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
            'replace_audioengine': True,
            'replace_tfa': True,
            'replace_init': False,
            'change_platform': False,
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
                'lib64/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'vendor/lib64/hw/audio.primary.*',
                'lib/hw/audio_policy.default.so',
                'lib64/hw/audio_policy.default.so',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'audioengine': [
                'lib/libaudiocomp*',
                'lib64/libaudiocomp*',
                'vendor/lib/libaudiocomp*',
                'vendor/lib64/libaudiocomp*',
                'lib/libaudioroute*',
                'lib64/libaudioroute*',
                'vendor/lib/libaudioroute*',
                'vendor/lib64/libaudioroute*',
                'lib/libaudioparam*',
                'lib64/libaudioparam*',
                'vendor/lib/libaudioparam*',
                'vendor/lib64/libaudioparam*'
            ],
            'tfa': [
                'etc/tfa*',
                'lib/libtfa*',
                'lib64/libtfa*',
                'vendor/lib/libtfa*',
                'vendor/lib64/libtfa*',
                'lib/libaudiotfa*',
                'lib64/libaudiotfa*'
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
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
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
                'lib64/hw/camera.*',
                'lib/lib3a.so',
                'lib64/lib3a.so',
                'lib/libcamalgo.so',
                'lib64/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib64/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib64/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib64/libfeatureio.so',
                'lib/libimageio.so',
                'lib64/libimageio.so',
                'lib/libmtkjpeg.so',
                'lib64/libmtkjpeg.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib64/hw/camera.*'
            ]
        }
    },
    'mt6797 (Helio X20/X25) kernel-3.18 (Android 5.1-7.1.2)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'replace_kernel': True,
            'replace_fstab': True,
            'replace_init': True,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_firmware': True,
            'replace_mddb': True,
            'replace_malidriver': True,
            'replace_audiodriver': True,
            'replace_audioengine': True,
            'replace_tfa': True,
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
            'change_platform': True,
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
                'initrd/fstab.mt6797'
            ],
            'init': [
                'initrd/init.mt6797.rc',
                'initrd/init.mt6797.usb.rc',
                'initrd/init.project.rc',
                'initrd/init.target.performance.rc'
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
                'lib/libGLES_mali.so',
                'lib64/libGLES_mali.so',
                'vendor/lib/libGLES_mali.so',
                'vendor/lib64/libGLES_mali.so',
                'lib/egl',
                'lib64/egl',
                'vendor/lib/egl',
                'vendor/lib64/egl',
                'vendor/lib/hw/vulkan.*',
                'vendor/lib64/hw/vulkan.*'
            ],
            'audiodriver': [
                'lib/hw/audio.primary.*',
                'lib64/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'vendor/lib64/hw/audio.primary.*',
                'lib/hw/audio_policy.default.so',
                'lib64/hw/audio_policy.default.so',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'etc/audio_policy.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'audioengine': [
                'lib/libaudiocomp*',
                'lib64/libaudiocomp*',
                'vendor/lib/libaudiocomp*',
                'vendor/lib64/libaudiocomp*',
                'lib/libaudioroute*',
                'lib64/libaudioroute*',
                'vendor/lib/libaudioroute*',
                'vendor/lib64/libaudioroute*',
                'lib/libaudioparam*',
                'lib64/libaudioparam*',
                'vendor/lib/libaudioparam*',
                'vendor/lib64/libaudioparam*'
            ],
            'tfa': [
                'etc/tfa*',
                'lib/libtfa*',
                'lib64/libtfa*',
                'vendor/lib/libtfa*',
                'vendor/lib64/libtfa*',
                'lib/libaudiotfa*',
                'lib64/libaudiotfa*'
            ],
            'libshowlogo': [
                'lib/libshowlogo.so',
                'lib64/libshowlogo.so',
                'vendor/lib/libshowlogo.so',
                'vendor/lib64/libshowlogo.so'
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
                'lib64/librilmtk.so',
                'lib64/librilutils.so',
                'lib64/mtk-ril.so',
                'vendor/lib/librilmtk.so',
                'vendor/lib/libmtk-ril.so',
                'vendor/lib/librilfusion.so',
                'vendor/lib/librilutilsmtk.so',
                'vendor/lib/libccci_util.so',
                'vendor/lib64/librilmtk.so',
                'vendor/lib64/libmtk-ril.so',
                'vendor/lib64/librilfusion.so',
                'vendor/lib64/librilutilsmtk.so',
                'vendor/lib64/libccci_util.so'
            ],
            'gralloc': [
                'lib/hw/gralloc.*',
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'lib64/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib64/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib64/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib64/libksensor.so',
                'vendor/lib/librgbwlightsensor.so',
                'vendor/lib64/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'lib64/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/lib64/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so',
                'vendor/lib64/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'lib64/hw/power.*',
                'vendor/lib/hw/power.*',
                'vendor/lib64/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'lib64/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib64/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib64/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib64/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'vendor/lib64/libbluetooth_relayer.so',
                'etc/bluetooth'
            ],
            'vibrator': [
                'lib/hw/vibrator.*',
                'lib64/hw/vibrator.*',
                'vendor/lib/hw/vibrator.*',
                'vendor/lib64/hw/vibrator.*'
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
                'lib64/libhardware_legacy.so',
                'lib/libwpa_client.so',
                'lib64/libwpa_client.so',
                'lib/libwifi-service.so',
                'lib64/libwifi-service.so',
                'etc/wifi',
                'vendor/firmware',
                'vendor/bin/netdiag',
                'vendor/lib/libem_wifi_jni.so',
                'vendor/lib64/libem_wifi_jni.so'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib64/hw/camera.*',
                'lib/lib3a.so',
                'lib64/lib3a.so',
                'lib/libcamalgo.so',
                'lib64/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib64/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib64/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib64/libfeatureio.so',
                'lib/libimageio.so',
                'lib64/libimageio.so',
                'lib/libimageio_plat_drv.so',
                'lib64/libimageio_plat_drv.so',
                'lib/libJpgDecPipe.so',
                'lib64/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib64/libJpgEncPipe.so',
                'lib/libmhalImageCodec.so',
                'lib64/libmhalImageCodec.so',
                'lib/libmtkcamera_client.so',
                'lib64/libmtkcamera_client.so',
                'lib/libmtkjpeg.so',
                'lib64/libmtkjpeg.so',
                'lib/libcam.paramsmgr.so',
                'lib64/libcam.paramsmgr.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib64/hw/camera.*',
                'vendor/lib/lib3a.so',
                'vendor/lib64/lib3a.so',
                'vendor/lib/libcamalgo.so',
                'vendor/lib64/libcamalgo.so',
                'vendor/lib/libcamdrv.so',
                'vendor/lib64/libcamdrv.so',
                'vendor/lib/libcameracustom.so',
                'vendor/lib64/libcameracustom.so',
                'vendor/lib/libfeatureio.so',
                'vendor/lib64/libfeatureio.so',
                'vendor/lib/libimageio.so',
                'vendor/lib64/libimageio.so',
                'vendor/lib/libimageio_plat_drv.so',
                'vendor/lib64/libimageio_plat_drv.so',
                'vendor/lib/libJpgDecPipe.so',
                'vendor/lib64/libJpgDecPipe.so',
                'vendor/lib/libJpgEncPipe.so',
                'vendor/lib64/libJpgEncPipe.so',
                'vendor/lib/libmhalImageCodec.so',
                'vendor/lib64/libmhalImageCodec.so',
                'vendor/lib/libmtkcamera_client.so',
                'vendor/lib64/libmtkcamera_client.so',
                'vendor/lib/libmtkjpeg.so',
                'vendor/lib64/libmtkjpeg.so',
                'vendor/lib/libcam.paramsmgr.so',
                'vendor/lib64/libcam.paramsmgr.so',
                'vendor/lib/libcam.camadapter.so',
                'vendor/lib64/libcam.camadapter.so',
                'vendor/lib/libcam.camnode.so',
                'vendor/lib64/libcam.camnode.so',
                'vendor/lib/libcam.camshot.so',
                'vendor/lib64/libcam.camshot.so',
                'vendor/lib/libcam.client.so',
                'vendor/lib64/libcam.client.so',
                'vendor/lib/libcam.device1.so',
                'vendor/lib64/libcam.device1.so',
                'vendor/lib/libcam.device3.so',
                'vendor/lib64/libcam.device3.so',
                'vendor/lib/libcam.exif.so',
                'vendor/lib64/libcam.exif.so',
                'vendor/lib/libcam.hal3a.v3.so',
                'vendor/lib64/libcam.hal3a.v3.so',
                'vendor/lib/libcam.halsensor.so',
                'vendor/lib64/libcam.halsensor.so',
                'vendor/lib/libcam.iopipe.so',
                'vendor/lib64/libcam.iopipe.so',
                'vendor/lib/libcam.metadataprovider.so',
                'vendor/lib64/libcam.metadataprovider.so',
                'vendor/lib/libcam.utils.so',
                'vendor/lib64/libcam.utils.so',
                'vendor/lib/libcam_utils.so',
                'vendor/lib64/libcam_utils.so',
                'vendor/lib/libfeatureiodrv.so',
                'vendor/lib64/libfeatureiodrv.so',
                'vendor/lib/libSwJpgCodec.so',
                'vendor/lib64/libSwJpgCodec.so'
            ]
        }
    },
    '未列芯片 (同平台自动识别)': {
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
            'replace_audioengine': False,
            'replace_tfa': False,
            'replace_init': False,
            'change_platform': True,
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
            'init': [
                'initrd/init.mt6735.rc',
                'initrd/init.mt6737.rc',
                'initrd/init.mt6735.usb.rc',
                'initrd/init.project.rc'
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
                'lib64/hw/audio.primary.*',
                'vendor/lib/hw/audio.primary.*',
                'vendor/lib64/hw/audio.primary.*',
                'lib/hw/audio_policy.default.so',
                'lib64/hw/audio_policy.default.so',
                'etc/audio_effects.conf',
                'vendor/etc/audio_effects.conf',
                'etc/audio_policy.conf',
                'vendor/etc/audio_policy.conf',
                'vendor/etc/audio_param',
                'vendor/etc/audio_device.xml'
            ],
            'audioengine': [
                'lib/libaudiocomp*',
                'lib64/libaudiocomp*',
                'vendor/lib/libaudiocomp*',
                'vendor/lib64/libaudiocomp*',
                'lib/libaudioroute*',
                'lib64/libaudioroute*',
                'vendor/lib/libaudioroute*',
                'vendor/lib64/libaudioroute*',
                'lib/libaudioparam*',
                'lib64/libaudioparam*',
                'vendor/lib/libaudioparam*',
                'vendor/lib64/libaudioparam*'
            ],
            'tfa': [
                'etc/tfa*',
                'lib/libtfa*',
                'lib64/libtfa*',
                'vendor/lib/libtfa*',
                'vendor/lib64/libtfa*',
                'lib/libaudiotfa*',
                'lib64/libaudiotfa*'
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
                'lib64/hw/gralloc.*',
                'vendor/lib/hw/gralloc.*',
                'vendor/lib64/hw/gralloc.*',
                'lib/libgralloc_extra.so',
                'lib64/libgralloc_extra.so',
                'vendor/lib/libgralloc_extra.so',
                'vendor/lib64/libgralloc_extra.so'
            ],
            'hwcomposer': [
                'lib/hw/hwcomposer.*',
                'lib64/hw/hwcomposer.*',
                'vendor/lib/hw/hwcomposer.*',
                'vendor/lib64/hw/hwcomposer.*'
            ],
            'sensors': [
                'lib/hw/sensors.*',
                'lib64/hw/sensors.*',
                'vendor/lib/hw/sensors.*',
                'vendor/lib64/hw/sensors.*',
                'vendor/lib/hw/lights.*',
                'vendor/lib64/hw/lights.*',
                'vendor/lib/libksensor.so',
                'vendor/lib64/libksensor.so',
                'vendor/lib/librgbwlightsensor.so',
                'vendor/lib64/librgbwlightsensor.so'
            ],
            'gps': [
                'lib/hw/gps.*',
                'lib64/hw/gps.*',
                'vendor/lib/hw/gps.*',
                'vendor/lib64/hw/gps.*',
                'vendor/etc/agps_profiles_conf2.xml',
                'vendor/lib/libviagpsrpc.so',
                'vendor/lib64/libviagpsrpc.so'
            ],
            'power': [
                'lib/hw/power.*',
                'lib64/hw/power.*',
                'vendor/lib/hw/power.*',
                'vendor/lib64/hw/power.*'
            ],
            'bluetooth': [
                'lib/hw/bluetooth.*',
                'lib64/hw/bluetooth.*',
                'vendor/lib/libbluetooth_mtk.so',
                'vendor/lib64/libbluetooth_mtk.so',
                'vendor/lib/libbluetooth_mtk_pure.so',
                'vendor/lib64/libbluetooth_mtk_pure.so',
                'vendor/lib/libbt-vendor.so',
                'vendor/lib64/libbt-vendor.so',
                'vendor/lib/libbluetooth_relayer.so',
                'vendor/lib64/libbluetooth_relayer.so',
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
                'lib64/libhardware_legacy.so',
                'lib/libwpa_client.so',
                'lib64/libwpa_client.so',
                'lib/libwifi-service.so',
                'lib64/libwifi-service.so',
                'etc/wifi',
                'vendor/firmware',
                'vendor/bin/netdiag',
                'vendor/lib/libem_wifi_jni.so',
                'vendor/lib64/libem_wifi_jni.so'
            ],
            'camera': [
                'lib/hw/camera.*',
                'lib64/hw/camera.*',
                'lib/lib3a.so',
                'lib64/lib3a.so',
                'lib/libcamalgo.so',
                'lib64/libcamalgo.so',
                'lib/libcamdrv.so',
                'lib64/libcamdrv.so',
                'lib/libcameracustom.so',
                'lib64/libcameracustom.so',
                'lib/libfeatureio.so',
                'lib64/libfeatureio.so',
                'lib/libimageio.so',
                'lib64/libimageio.so',
                'lib/libimageio_plat_drv.so',
                'lib64/libimageio_plat_drv.so',
                'lib/libJpgDecPipe.so',
                'lib64/libJpgDecPipe.so',
                'lib/libJpgEncPipe.so',
                'lib64/libJpgEncPipe.so',
                'lib/libmhalImageCodec.so',
                'lib64/libmhalImageCodec.so',
                'lib/libmtkcamera_client.so',
                'lib64/libmtkcamera_client.so',
                'lib/libmtkjpeg.so',
                'lib64/libmtkjpeg.so',
                'lib/libcam.paramsmgr.so',
                'lib64/libcam.paramsmgr.so',
                'vendor/lib/hw/camera.*',
                'vendor/lib64/hw/camera.*',
                'vendor/lib/lib3a.so',
                'vendor/lib64/lib3a.so',
                'vendor/lib/libcamalgo.so',
                'vendor/lib64/libcamalgo.so',
                'vendor/lib/libcamdrv.so',
                'vendor/lib64/libcamdrv.so',
                'vendor/lib/libcameracustom.so',
                'vendor/lib64/libcameracustom.so',
                'vendor/lib/libfeatureio.so',
                'vendor/lib64/libfeatureio.so',
                'vendor/lib/libimageio.so',
                'vendor/lib64/libimageio.so',
                'vendor/lib/libimageio_plat_drv.so',
                'vendor/lib64/libimageio_plat_drv.so',
                'vendor/lib/libJpgDecPipe.so',
                'vendor/lib64/libJpgDecPipe.so',
                'vendor/lib/libJpgEncPipe.so',
                'vendor/lib64/libJpgEncPipe.so',
                'vendor/lib/libmhalImageCodec.so',
                'vendor/lib64/libmhalImageCodec.so',
                'vendor/lib/libmtkcamera_client.so',
                'vendor/lib64/libmtkcamera_client.so',
                'vendor/lib/libmtkjpeg.so',
                'vendor/lib64/libmtkjpeg.so',
                'vendor/lib/libcam.paramsmgr.so',
                'vendor/lib64/libcam.paramsmgr.so',
                'vendor/lib/libcam.camadapter.so',
                'vendor/lib64/libcam.camadapter.so',
                'vendor/lib/libcam.camnode.so',
                'vendor/lib64/libcam.camnode.so',
                'vendor/lib/libcam.camshot.so',
                'vendor/lib64/libcam.camshot.so',
                'vendor/lib/libcam.client.so',
                'vendor/lib64/libcam.client.so',
                'vendor/lib/libcam.device1.so',
                'vendor/lib64/libcam.device1.so',
                'vendor/lib/libcam.device3.so',
                'vendor/lib64/libcam.device3.so',
                'vendor/lib/libcam.exif.so',
                'vendor/lib64/libcam.exif.so',
                'vendor/lib/libcam.hal3a.v3.so',
                'vendor/lib64/libcam.hal3a.v3.so',
                'vendor/lib/libcam.halsensor.so',
                'vendor/lib64/libcam.halsensor.so',
                'vendor/lib/libcam.iopipe.so',
                'vendor/lib64/libcam.iopipe.so',
                'vendor/lib/libcam.metadataprovider.so',
                'vendor/lib64/libcam.metadataprovider.so',
                'vendor/lib/libcam.utils.so',
                'vendor/lib64/libcam.utils.so',
                'vendor/lib/libcam_utils.so',
                'vendor/lib64/libcam_utils.so',
                'vendor/lib/libfeatureiodrv.so',
                'vendor/lib64/libfeatureiodrv.so',
                'vendor/lib/libSwJpgCodec.so',
                'vendor/lib64/libSwJpgCodec.so'
            ]
        }
    },
    'LK去警告 (兼容大多数安卓版本, 去Orange/Red警告+5s延时)': {
        'partitions': {
        },
        'flags': {
            'lk_patch_mode': True
        },
        'replace': {
        }
    },
    '仅移植Recovery (只输出recovery)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'recovery_only_mode': True,
            'replace_kernel': True,
            'selinux_permissive': True,
            'enable_adb': True,
            'replace_fstab': False,
            'replace_init': False
        },
        'replace': {
            'kernel': [
                'kernel',
                'kernel.gz'
            ],
            'fstab': [
                'initrd/fstab',
                'initrd/fstab.mt6572',
                'initrd/fstab.mt6582',
                'initrd/fstab.mt6580',
                'initrd/fstab.mt6735',
                'initrd/fstab.mt6737',
                'initrd/fstab.mt6750',
                'initrd/fstab.mt6755',
                'initrd/fstab.mt6797',
                'initrd/etc/recovery.fstab'
            ],
            'init': [
                'initrd/init.rc',
                'initrd/init.recovery.rc',
                'initrd/init.mt6572.rc',
                'initrd/init.mt6582.rc',
                'initrd/init.mt6580.rc',
                'initrd/init.mt6735.rc',
                'initrd/init.mt6737.rc',
                'initrd/init.mt6750.rc',
                'initrd/init.mt6755.rc',
                'initrd/init.mt6797.rc'
            ]
        }
    },
    '仅移植内核 (只输出boot)': {
        'partitions': {
        },
        'flags': {
            'generate_script': False,
            'kernel_only_mode': True,
            'replace_kernel': True,
            'selinux_permissive': True,
            'enable_adb': True
        },
        'replace': {
            'kernel': [
                'kernel',
                'kernel.gz'
            ]
        }
    }
}

_configs_path = op.join(_ROOT, "configs.json")
if op.isfile(_configs_path):
    with open(_configs_path, 'r', encoding='utf-8-sig') as c:
        support_chipset_portstep = json.load(c)
else:
    with open(_configs_path, 'w', encoding='utf-8') as c:
        json.dump(support_chipset_portstep, c, indent=4, ensure_ascii=False)

support_chipset = list(support_chipset_portstep.keys())
support_packtype = ['zip', 'img']
ostype, arch = archdetect.retTypeAndMachine()
ext_ext = '.exe' if ostype == 'win' else ''

# binarys
make_ext4fs_bin = op.join(_ROOT, "bin", ostype, arch, "make_ext4fs"+ext_ext)
magiskboot_bin = op.join(_ROOT, "bin", ostype, arch, "magiskboot"+ext_ext)
simg2img_bin = op.join(_ROOT, "bin", ostype, arch, "simg2img"+ext_ext)
img2simg_bin = op.join(_ROOT, "bin", ostype, arch, "img2simg"+ext_ext)
