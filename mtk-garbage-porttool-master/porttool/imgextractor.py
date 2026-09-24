import os
import sys
import string
import struct
import traceback
import shutil
import re
from . import ext4

SPARSE_HEADER_MAGIC = 0xED26FF3A   # Android sparse image 魔数（位于文件偏移 0）
EXT4_SUPER_MAGIC = 0xEF53          # ext4 文件系统魔数（位于超级块偏移 0x438）
EXT4_SPARSE_HEADER_LEN = 28
EXT4_CHUNK_HEADER_SIZE = 12


class ext4_file_header(object):
    def __init__(self, buf):
        (self.magic,
         self.major,
         self.minor,
         self.file_header_size,
         self.chunk_header_size,
         self.block_size,
         self.total_blocks,
         self.total_chunks,
         self.crc32) = struct.unpack('<I4H4I', buf)


class ext4_chunk_header(object):
    def __init__(self, buf):
        (self.type,
         self.reserved,
         self.chunk_size,
         self.total_size) = struct.unpack('<2H2I', buf)


def is_sparse_image(target):
    """
    严格判断文件是否为 Android sparse image。
    sparse 魔数必须位于文件偏移 0，并校验版本/块大小/头部大小等关键字段，
    避免把内容中偶然出现 0xED26FF3A 字节序列的 raw ext4 镜像误判为 sparse。
    """
    try:
        with open(target, "rb") as f:
            buf = f.read(EXT4_SPARSE_HEADER_LEN)
        if len(buf) < EXT4_SPARSE_HEADER_LEN:
            return False
        hdr = ext4_file_header(buf)
        if hdr.magic != SPARSE_HEADER_MAGIC:
            return False
        if hdr.major != 1:
            return False
        if hdr.file_header_size < EXT4_SPARSE_HEADER_LEN:
            return False
        if hdr.chunk_header_size < EXT4_CHUNK_HEADER_SIZE:
            return False
        bs = hdr.block_size
        # block_size 必须是 512~65536 之间的 2 的幂
        if bs < 512 or bs > 65536 or (bs & (bs - 1)) != 0:
            return False
        if hdr.total_blocks == 0 or hdr.total_chunks == 0:
            return False
        return True
    except Exception:
        return False


class Extractor(object):
    def __init__(self):
        self.FileName = ""
        self.BASE_DIR = ""
        self.OUTPUT_IMAGE_FILE = ""
        self.EXTRACT_DIR = ""
        self.BLOCK_SIZE = 4096
        self.TYPE_IMG = 'system'
        self.context = []
        self.fsconfig = []

    def __remove(self, path):
        if os.path.isfile(path):
            os.remove(path)  # remove the file
        elif os.path.isdir(path):
            shutil.rmtree(path)  # remove dir and all contains
        else:
            raise ValueError("file {} is not a file or dir.".format(path))

    def __logtb(self, ex, ex_traceback=None):
        if ex_traceback is None:
            ex_traceback = ex.__traceback__
        tb_lines = [line.rstrip('\n') for line in
                    traceback.format_exception(ex.__class__, ex, ex_traceback)]
        return '\n'.join(tb_lines)

    def __file_name(self,file_path):
        name = os.path.basename(file_path).split('.')[0]
        name = name.split('-')[0]
       # name = name.split('_')[0]
        name = name.split(' ')[0]
        name = name.split('+')[0]
        name = name.split('{')[0]
        name = name.split('(')[0]
        return name

    def __appendf(self, msg, log_file):
        with open(log_file, 'a', newline='\n') as file:
            print(msg, file=file)

    def __getperm(self, arg):
        if len(arg) < 9 or len(arg) > 10:
            return
        if len(arg) > 8:
            arg = arg[1:]
        oor, ow, ox, gr, gw, gx, wr, ww, wx = list(arg)
        o, g, w, s = 0, 0, 0, 0
        if oor == 'r': o += 4
        if ow == 'w': o += 2
        if ox == 'x': o += 1
        if ox == 'S': s += 4
        if ox == 's': s += 4; o += 1
        if gr == 'r': g += 4
        if gw == 'w': g += 2
        if gx == 'x': g += 1
        if gx == 'S': s += 2
        if gx == 's': s += 2; g += 1
        if wr == 'r': w += 4
        if ww == 'w': w += 2
        if wx == 'x': w += 1
        if wx == 'T': s += 1
        if wx == 't': s += 1; w += 1
        return str(s) + str(o) + str(g) + str(w)

    def __ext4extractor(self):
        fs_config_file = self.FileName + '_fs_config'
        fuking_symbols='\\^$.|?*+(){}[]'
        contexts = self.CONFING_DIR + os.sep + self.FileName + "_file_contexts" #08.05.18
        def scan_dir(root_inode, root_path=""):
            for entry_name, entry_inode_idx, entry_type in root_inode.open_dir():
                if entry_name in ['.', '..'] or entry_name.endswith(' (2)'):
                    continue
                entry_inode = root_inode.volume.get_inode(entry_inode_idx, entry_type)
                entry_inode_path = root_path + '/' + entry_name
                mode = self.__getperm(entry_inode.mode_str)
                uid = entry_inode.inode.i_uid
                gid = entry_inode.inode.i_gid
                con = ''
                cap = ''
                for i in list(entry_inode.xattrs()):
                    if i[0] == 'security.selinux':
                        con = i[1].decode('utf8')[:-1]
                    elif i[0] == 'security.capability':
                        raw_cap = struct.unpack("<5I", i[1])
                        if raw_cap[1] > 65535:
                            cap = '' + str(hex(int('%04x%04x' % (raw_cap[3], raw_cap[1]), 16)))
                        else:
                            cap = '' + str(hex(int('%04x%04x%04x' % (raw_cap[3], raw_cap[2], raw_cap[1]), 16)))
                        cap = ' capabilities={cap}'.format(cap=cap)
                if entry_inode.is_dir:
                    dir_target = self.EXTRACT_DIR + entry_inode_path.replace(' ','_').replace('"','')
                    if not os.path.isdir(dir_target):
                        os.makedirs(dir_target)
                    if os.name == 'posix':
                        os.chmod(dir_target, int(mode, 8))
                        os.chown(dir_target, uid, gid)
                    scan_dir(entry_inode, entry_inode_path)
                    if cap == '' and con == '':
                        tmppath=self.DIR + entry_inode_path
                        if (tmppath).find(' ',1,len(tmppath))>0:
                            spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                            if not os.path.isfile(spaces_file):
                                f = open(spaces_file, 'tw', encoding='utf-8')
                                self.__appendf(tmppath, spaces_file)
                                f.close()
                            else:
                                self.__appendf(tmppath, spaces_file)
                            tmppath=tmppath.replace(' ', '_')
                            self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode))
                        else:    
                            self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode))
                    else:
                        if cap == '':
                            tmppath=self.DIR + entry_inode_path
                            if (tmppath).find(' ',1,len(tmppath))>0:
                                spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                if not os.path.isfile(spaces_file):
                                    f = open(spaces_file, 'tw', encoding='utf-8')
                                    self.__appendf(tmppath, spaces_file)
                                    f.close()
                                else:
                                    self.__appendf(tmppath, spaces_file)
                                tmppath=tmppath.replace(' ', '_')
                                self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode))
                            else:    
                                self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode))
                            for fuk_symb in fuking_symbols:
                                tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                            self.context.append('/%s %s' % (tmppath, con))
                        else:
                            if con == '':
                                tmppath=self.DIR + entry_inode_path
                                if (tmppath).find(' ',1,len(tmppath))>0:
                                    spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                    if not os.path.isfile(spaces_file):
                                        f = open(spaces_file, 'tw', encoding='utf-8')
                                        self.__appendf(tmppath, spaces_file)
                                        f.close()
                                    else:
                                        self.__appendf(tmppath, spaces_file)
                                    tmppath=tmppath.replace(' ', '_')
                                    self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode + cap))
                                else:    
                                    self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap))
                            else:
                                tmppath=self.DIR + entry_inode_path
                                if (tmppath).find(' ',1,len(tmppath))>0:
                                    spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                    if not os.path.isfile(spaces_file):
                                        f = open(spaces_file, 'tw', encoding='utf-8')
                                        self.__appendf(tmppath, spaces_file)
                                        f.close()
                                    else:
                                        self.__appendf(tmppath, spaces_file)
                                    tmppath=tmppath.replace(' ', '_')
                                    self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode + cap))
                                else:    
                                    self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap))
                                for fuk_symb in fuking_symbols:
                                    tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                self.context.append('/%s %s' % (tmppath, con))
                elif entry_inode.is_file:
                    raw = entry_inode.open_read().read()
                    wdone = None
                    if os.name == 'nt':
                        if entry_name.endswith('/'):
                            entry_name = entry_name[:-1]
                        file_target = self.EXTRACT_DIR + entry_inode_path.replace('/', os.sep).replace(' ','_').replace('"','')
                        if not os.path.isdir(os.path.dirname(file_target)):
                            os.makedirs(os.path.dirname(file_target))
                        with open(file_target, 'wb') as out:
                            out.write(raw)
                    if os.name == 'posix':
                        file_target = self.EXTRACT_DIR + entry_inode_path.replace(' ','_').replace('"','')
                        if not os.path.isdir(os.path.dirname(file_target)):
                            os.makedirs(os.path.dirname(file_target))
                        with open(file_target, 'wb') as out:
                            out.write(raw)
                        os.chmod(file_target, int(mode, 8))
                        os.chown(file_target, uid, gid)
                    if cap == '' and con == '':
                        tmppath=self.DIR + entry_inode_path
                        if (tmppath).find(' ',1,len(tmppath))>0:
                            spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                            if not os.path.isfile(spaces_file):
                                f = open(spaces_file, 'tw', encoding='utf-8')
                                self.__appendf(tmppath, spaces_file)
                                f.close()
                            else:
                                self.__appendf(tmppath, spaces_file)
                            tmppath=tmppath.replace(' ', '_')
                            self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode))
                        else:    
                            self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode))
                    else:
                        if cap == '':
                            tmppath=self.DIR + entry_inode_path
                            if (tmppath).find(' ',1,len(tmppath))>0:
                                spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                if not os.path.isfile(spaces_file):
                                    f = open(spaces_file, 'tw', encoding='utf-8')
                                    self.__appendf(tmppath, spaces_file)
                                    f.close()
                                else:
                                    self.__appendf(tmppath, spaces_file)
                                tmppath=tmppath.replace(' ', '_')
                                self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode))
                            else:    
                                self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode))
                            for fuk_symb in fuking_symbols:
                                tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                            self.context.append('/%s %s' % (tmppath, con))
                        else:
                            if con == '':
                                tmppath=self.DIR + entry_inode_path
                                if (tmppath).find(' ',1,len(tmppath))>0:
                                    spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                    if not os.path.isfile(spaces_file):
                                        f = open(spaces_file, 'tw', encoding='utf-8')
                                        self.__appendf(tmppath, spaces_file)
                                        f.close()
                                    else:
                                        self.__appendf(tmppath, spaces_file)
                                    tmppath=tmppath.replace(' ', '_')
                                    self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode + cap))
                                else:    
                                    self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap))
                            else:
                                tmppath=self.DIR + entry_inode_path
                                if (tmppath).find(' ',1,len(tmppath))>0:
                                    spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                    if not os.path.isfile(spaces_file):
                                        f = open(spaces_file, 'tw', encoding='utf-8')
                                        self.__appendf(tmppath, spaces_file)
                                        f.close()
                                    else:
                                        self.__appendf(tmppath, spaces_file)
                                    tmppath=tmppath.replace(' ', '_')
                                    self.fsconfig.append('%s %s %s %s' % (tmppath, uid, gid, mode + cap))
                                else:    
                                    self.fsconfig.append('%s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap))
                                for fuk_symb in fuking_symbols:
                                    tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                self.context.append('/%s %s' % (tmppath, con))
                elif entry_inode.is_symlink:
                    try:
                        link_target = entry_inode.open_read().read().decode("utf8")
                        target = self.EXTRACT_DIR + entry_inode_path.replace(' ', '_')
                        if cap == '' and con == '':
                            tmppath=self.DIR + entry_inode_path
                            if (tmppath).find(' ',1,len(tmppath))>0:
                                spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                if not os.path.isfile(spaces_file):
                                    f = open(spaces_file, 'tw', encoding='utf-8')
                                    self.__appendf(tmppath, spaces_file)
                                    f.close()
                                else:
                                    self.__appendf(tmppath, spaces_file)
                                tmppath=tmppath.replace(' ', '_')
                                self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode, link_target))
                            else:    
                                self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode, link_target))
                        else:
                            if cap == '':
                                tmppath=self.DIR + entry_inode_path
                                if (tmppath).find(' ',1,len(tmppath))>0:
                                    spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                    if not os.path.isfile(spaces_file):
                                        f = open(spaces_file, 'tw', encoding='utf-8')
                                        self.__appendf(tmppath, spaces_file)
                                        f.close()
                                    else:
                                        self.__appendf(tmppath, spaces_file)
                                    tmppath=tmppath.replace(' ', '_')
                                    self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode, link_target))
                                else:    
                                    self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode, link_target))
                                for fuk_symb in fuking_symbols:
                                    tmppath=tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                self.context.append('/%s %s' % (tmppath, con))
                            else:
                                if con == '':
                                    tmppath=self.DIR + entry_inode_path
                                    if (tmppath).find(' ',1,len(tmppath))>0:
                                        spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                        if not os.path.isfile(spaces_file):
                                            f = open(spaces_file, 'tw', encoding='utf-8')
                                            self.__appendf(tmppath, spaces_file)
                                            f.close()
                                        else:
                                            self.__appendf(tmppath, spaces_file)
                                        tmppath=tmppath.replace(' ', '_')
                                        self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode + cap, link_target))
                                    else:    
                                        self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap, link_target))
                                else:
                                    tmppath=self.DIR + entry_inode_path
                                    if (tmppath).find(' ',1,len(tmppath))>0:
                                        spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                        if not os.path.isfile(spaces_file):
                                            f = open(spaces_file, 'tw', encoding='utf-8')
                                            self.__appendf(tmppath, spaces_file)
                                            f.close()
                                        else:
                                            self.__appendf(tmppath, spaces_file)
                                        tmppath=tmppath.replace(' ', '_')
                                        self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode + cap, link_target))
                                    else:    
                                        self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap, link_target))
                                    for fuk_symb in fuking_symbols:
                                        tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                    self.context.append('/%s %s' % (tmppath, con))
                        if os.path.islink(target):
                            try:
                                os.remove(target)
                            except:
                                pass
                        if os.path.isfile(target):
                            try:
                                os.remove(target)
                            except:
                                pass
                        if os.name == 'posix':
                            os.symlink(link_target, target)
                        if os.name == 'nt':
                            with open(target.replace('/', os.sep), 'wb') as out:
                                tmp = bytes.fromhex('213C73796D6C696E6B3EFFFE')
                                for index in list(link_target):
                                    tmp = tmp + struct.pack('>sx', index.encode('utf-8'))
                                out.write(tmp + struct.pack('xx'))
                        if not all(c in string.printable for c in link_target):
                            pass
                        if entry_inode_path[1:] == entry_name or link_target[1:] == entry_name:
                            self.symlinks.append('%s %s' % (link_target, entry_inode_path[1:]))
                        else:
                            self.symlinks.append('%s %s' % (link_target, self.DIR + entry_inode_path))
                    except:
                        try:
                            link_target_block = int.from_bytes(entry_inode.open_read().read(), "little")
                            link_target = root_inode.volume.read(link_target_block * root_inode.volume.block_size, entry_inode.inode.i_size).decode("utf8")
                            target = self.EXTRACT_DIR + entry_inode_path.replace(' ', '_')
                            if link_target and all(c in string.printable for c in link_target):
                                if cap == '' and con == '':
                                    tmppath=self.DIR + entry_inode_path
                                    if (tmppath).find(' ',1,len(tmppath))>0:
                                        spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                        if not os.path.isfile(spaces_file):
                                            f = open(spaces_file, 'tw', encoding='utf-8')
                                            self.__appendf(tmppath, spaces_file)
                                            f.close()
                                        else:
                                            self.__appendf(tmppath, spaces_file)
                                        tmppath=tmppath.replace(' ', '_')
                                        self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode, link_target))
                                    else:    
                                        self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode, link_target))
                                else:
                                    if cap == '':
                                        tmppath=self.DIR + entry_inode_path
                                        if (tmppath).find(' ',1,len(tmppath))>0:
                                            spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                            if not os.path.isfile(spaces_file):
                                                f = open(spaces_file, 'tw', encoding='utf-8')
                                                self.__appendf(tmppath, spaces_file)
                                                f.close()
                                            else:
                                                self.__appendf(tmppath, spaces_file)
                                            tmppath=tmppath.replace(' ', '_')
                                            self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode, link_target))
                                        else:    
                                            self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode, link_target))
                                        for fuk_symb in fuking_symbols:
                                            tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                        self.context.append('/%s %s' % (tmppath, con))
                                    else:
                                        if con == '':
                                            tmppath=self.DIR + entry_inode_path
                                            if (tmppath).find(' ',1,len(tmppath))>0:
                                                spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                                if not os.path.isfile(spaces_file):
                                                    f = open(spaces_file, 'tw', encoding='utf-8')
                                                    self.__appendf(tmppath, spaces_file)
                                                    f.close()
                                                else:
                                                    self.__appendf(tmppath, spaces_file)
                                                tmppath=tmppath.replace(' ', '_')
                                                self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode + cap, link_target))
                                            else:    
                                                self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap, link_target))
                                        else:
                                            tmppath=self.DIR + entry_inode_path
                                            if (tmppath).find(' ',1,len(tmppath))>0:
                                                spaces_file=self.BASE_MYDIR + 'config' + os.sep + self.FileName + '_space.txt'
                                                if not os.path.isfile(spaces_file):
                                                    f = open(spaces_file, 'tw', encoding='utf-8')
                                                    self.__appendf(tmppath, spaces_file)
                                                    f.close()
                                                else:
                                                    self.__appendf(tmppath, spaces_file)
                                                tmppath=tmppath.replace(' ', '_')
                                                self.fsconfig.append('%s %s %s %s %s' % (tmppath, uid, gid, mode + cap, link_target))
                                            else:    
                                                self.fsconfig.append('%s %s %s %s %s' % (self.DIR + entry_inode_path, uid, gid, mode + cap, link_target))
                                            for fuk_symb in fuking_symbols:
                                                tmppath=tmppath.replace(fuk_symb, '\\'+fuk_symb)
                                            self.context.append('/%s %s' % (tmppath, con))
                                if os.name == 'posix':
                                    os.symlink(link_target, target)
                                if os.name == 'nt':
                                    with open(target.replace('/', os.sep), 'wb') as out:
                                        tmp = bytes.fromhex('213C73796D6C696E6B3EFFFE')
                                        for index in list(link_target):
                                            tmp = tmp + struct.pack('>sx', index.encode('utf-8'))
                                        out.write(tmp + struct.pack('xx'))
                            else:
                                pass
                        except:
                            pass
                            
        dir_my = self.CONFING_DIR + os.sep
        if not os.path.isdir(dir_my):
            os.makedirs(dir_my)
       # f = open(dir_my + self.FileName + '_pack.sh', 'tw', encoding='utf-8')
       # self.__appendf('make_ext4fs -T -1 -S ./file_contexts -C ./fs_config -l ' +str(os.path.getsize(self.OUTPUT_IMAGE_FILE))+ ' -a /'+self.FileName+' "$outdir"/'+self.FileName+'.new.img '+self.FileName+'', dir_my + self.FileName + '_pack.sh')
       # f.close()
       # f = open(dir_my + self.FileName + '_pack_sparse.sh', 'tw', encoding='utf-8')
       # self.__appendf('make_ext4fs -s -T -1 -S ./file_contexts -C ./fs_config -l ' +str(os.path.getsize(self.OUTPUT_IMAGE_FILE))+ ' -a /'+self.FileName+' "$outdir"/'+self.FileName+'.new.img '+self.FileName+'', dir_my + self.FileName + '_pack_sparse.sh')
       # f.close()
        f = open(dir_my + self.FileName + '_size.txt', 'tw', encoding='utf-8')
        self.__appendf(os.path.getsize(self.OUTPUT_IMAGE_FILE), dir_my + self.FileName + '_size.txt')
        f.close()
       # f = open(dir_my + self.FileName + '_name.txt', 'tw', encoding='utf-8')
       # self.__appendf(os.path.basename(self.OUTPUT_IMAGE_FILE).replace(".img", ""), dir_my + self.FileName + '_name.txt')
       # f.close()
        with open(self.OUTPUT_IMAGE_FILE, 'rb') as file:
            root = ext4.Volume(file).root
            dirlist = []
            for file_name, inode_idx, file_type in root.open_dir():
                dirlist.append(file_name)
            dirr = self.__file_name(os.path.basename(self.OUTPUT_IMAGE_FILE).split('.')[0]) #11.05.18
            setattr(self, 'DIR', dirr)
            scan_dir(root)          
            for c in self.fsconfig:
                if dirr == 'vendor':
                    self.fsconfig.insert(0, '/' + ' 0 2000 0755')
                    self.fsconfig.insert(1, dirr + ' 0 2000 0755')
                elif dirr == 'system':
                    self.fsconfig.insert(0, '/' + ' 0 0 0755')
                    self.fsconfig.insert(1, '/' + 'lost+found' + ' 0 0 0700')
                    self.fsconfig.insert(2, dirr + ' 0 0 0755')
                else:
                    self.fsconfig.insert(0, '/' + ' 0 0 0755')
                    self.fsconfig.insert(1, dirr + ' 0 0 0755')
                break 

            self.__appendf('\n'.join(self.fsconfig), self.CONFING_DIR + os.sep + fs_config_file)
            if self.context: #11.05.18
                self.context.sort() #11.05.18
                for c in self.context:
                    if re.search('lost..found', c):
                        self.context.insert(0, '/' + ' ' + c.split(" ")[1])                    
                        self.context.insert(1, '/' + dirr +'(/.*)? ' + c.split(" ")[1])
                        self.context.insert(2, '/' + dirr + ' ' + c.split(" ")[1])
                        self.context.insert(3, '/' + dirr + '/lost+found' + ' ' + c.split(" ")[1])
                        break

                for c in self.context:
                    if re.search('/system/system/build..prop ', c):
                        self.context.insert(3, '/lost+found' + ' u:object_r:rootfs:s0')
                        self.context.insert(4, '/' + dirr + '/' + dirr + '(/.*)? ' + c.split(" ")[1])
                        break
                self.__appendf('\n'.join(self.context), contexts) #11.05.18

    def __converSimgToImg(self, target):
        """将 Android sparse image 转换为 raw ext4 image"""
        out_target = target.replace(".img", ".raw.img")
        with open(target, "rb") as img_file:
            header = ext4_file_header(img_file.read(EXT4_SPARSE_HEADER_LEN))
            # 文件头大小非标准时，跳过多余的头部字节
            if header.file_header_size > EXT4_SPARSE_HEADER_LEN:
                img_file.seek(header.file_header_size - EXT4_SPARSE_HEADER_LEN, 1)
            with open(out_target, "wb") as raw_out:
                while header.total_chunks > 0:
                    chunk = ext4_chunk_header(img_file.read(EXT4_CHUNK_HEADER_SIZE))
                    chunk_data_size = chunk.total_size - header.chunk_header_size
                    out_bytes = chunk.chunk_size * header.block_size
                    if chunk.type == 0xCAC1:      # CHUNK_TYPE_RAW：原样复制数据
                        if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                            img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                        raw_out.write(img_file.read(chunk_data_size))
                    elif chunk.type == 0xCAC2:    # CHUNK_TYPE_FILL：用 4 字节填充值重复填满
                        if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                            img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                        fill = img_file.read(4)
                        if chunk_data_size > 4:
                            img_file.read(chunk_data_size - 4)
                        repeats = out_bytes // 4
                        raw_out.write(fill * repeats)
                        rem = out_bytes % 4
                        if rem:
                            raw_out.write(fill[:rem])
                    elif chunk.type == 0xCAC3:    # CHUNK_TYPE_DONT_CARE：输出 0
                        if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                            img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                        if chunk_data_size:
                            img_file.read(chunk_data_size)
                        raw_out.write(b'\x00' * out_bytes)
                    else:                        # CHUNK_TYPE_CRC32 / 未知类型：跳过输入数据，输出 0
                        if header.chunk_header_size > EXT4_CHUNK_HEADER_SIZE:
                            img_file.seek(header.chunk_header_size - EXT4_CHUNK_HEADER_SIZE, 1)
                        if chunk_data_size:
                            img_file.read(chunk_data_size)
                        raw_out.write(b'\x00' * out_bytes)
                    header.total_chunks -= 1
        self.OUTPUT_IMAGE_FILE = out_target
    
    def fixmoto(self, input_file):
        if os.path.exists(input_file) == False:
            return
        output_file=input_file + "_"
        if os.path.exists(output_file) == True:
            try:
                os.remove(output_file)
            except:
                pass
        with open(input_file, 'rb') as f:
            data = f.read(500000)
        moto = re.search(b'\x4d\x4f\x54\x4f', data)
        if not moto:
            return
        result = []
        for i in re.finditer(b'\x53\xEF', data):
            result.append(i.start() - 1080)
        offset = 0
        for i in result:
            if data[i] == 0:
                offset = i
                break        
        if offset > 0:
            with open(output_file, 'wb') as o, open(input_file, 'rb') as f:
                data = f.seek(offset)
                data = f.read(15360)
                if data:
                    devnull = o.write(data)
        try:
                os.remove(input_file)
                os.rename(output_file, input_file)
        except:
                pass

    def __getTypeTarget(self, target):
        """
        检测镜像类型：
          'simg' -> Android sparse image（解包前需先转 raw）
          'img'  -> raw ext4 image
        """
        _, file_extension = os.path.splitext(target)
        if file_extension == '.img' and is_sparse_image(target):
            return 'simg'
        return 'img'

    def main(self, target, output_dir):
        self.BASE_DIR = (os.path.realpath(os.path.dirname(target)) + os.sep)
        self.BASE_MYDIR = output_dir + os.sep
        self.EXTRACT_DIR = os.path.realpath(os.path.dirname(output_dir)) + os.sep + self.__file_name(os.path.basename(output_dir)) #output_dir
        self.OUTPUT_IMAGE_FILE = self.BASE_DIR + os.path.basename(target)
        self.OUTPUT_MYIMAGE_FILE = os.path.basename(target)
        self.MYFileName = os.path.basename(self.OUTPUT_IMAGE_FILE).replace(".img", "")
        self.FileName = self.__file_name(os.path.basename(target))
        target_type = self.__getTypeTarget(target)
        if sys.argv.__len__() == 3:
            self.CONFING_DIR = sys.argv[2] + os.sep + 'config'
        else:
            self.CONFING_DIR = output_dir + os.sep + ".." + os.sep + 'config'        
        if target_type == 'simg':
            print(".....Convert %s to %s" % (os.path.basename(target), os.path.basename(target).replace(".img", ".raw.img")))
            self.__converSimgToImg(target)
            with open(os.path.abspath(self.OUTPUT_IMAGE_FILE), 'rb') as f:
                data = f.read(500000)
            moto = re.search(b'\x4d\x4f\x54\x4f', data)
            if moto:
                print(".....Finding MOTO structure! Fixing.....")
                self.fixmoto(os.path.abspath(self.OUTPUT_IMAGE_FILE))
            print(".....Extraction from %s to %s" % (os.path.basename(target), os.path.basename(self.EXTRACT_DIR)))
            self.__ext4extractor()
            print(".....Done! All extraction in %s" % (os.path.basename(self.EXTRACT_DIR)))
            # 清理 sparse 转换生成的中间 raw 镜像（与源镜像同级，避免残留）
            _intermediate = os.path.abspath(self.OUTPUT_IMAGE_FILE)
            if _intermediate != os.path.abspath(target) and os.path.exists(_intermediate):
                try:
                    os.remove(_intermediate)
                except Exception:
                    pass
        if target_type == 'img':
            with open(os.path.abspath(self.OUTPUT_IMAGE_FILE), 'rb') as f:
                data = f.read(500000)
            moto = re.search(b'\x4d\x4f\x54\x4f', data)
            if moto:
                print(".....Finding MOTO structure! Fixing.....")
                self.fixmoto(os.path.abspath(self.OUTPUT_IMAGE_FILE))
            print(".....Extraction from %s to %s" % (os.path.basename(target), os.path.basename(self.EXTRACT_DIR)))
            self.__ext4extractor()
            print(".....Done! All extraction in %s" % (os.path.basename(self.EXTRACT_DIR)))

if __name__ == '__main__':
    if sys.argv.__len__() == 3:
        Extractor().main(sys.argv[1], (sys.argv[2] + os.sep + os.path.basename(sys.argv[1]).split('.')[0]))
    else:
        if sys.argv.__len__() == 2:
            if not os.path.isdir("out"):
                os.makedirs("out")
            Extractor().main(sys.argv[1], "out" + os.sep + os.path.basename(sys.argv[1]).split('.')[0])