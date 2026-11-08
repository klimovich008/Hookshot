# SPDX-License-Identifier: GPL-3.0-or-later
"""Game-free extraction of the production compute-layout parser/lookup/table.
Synthetic control bytes only; no game assets or GPU.
"""
from pathlib import Path
import argparse,subprocess,tempfile
import os
import re

def block(s,marker):
 start=s.index(marker);at=s.index('{',start)+1;depth=1
 while depth:depth+=(s[at]=='{')-(s[at]=='}');at+=1
 return s[start:at]

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
p.add_argument('--cxx',default='clang++')
p.add_argument('--linker',type=Path)
a=p.parse_args()
bank=a.source/'gpu/vk/vk_bank.cpp'
s=bank.read_text(encoding='utf-8-sig')
parts=[block(s,'struct CsLayout')+';']
fixed='CsLayout cs_layout_of(' in s
if fixed:
 declaration=re.search(r'^(?:thread_local\s+)?const uint8_t\* seed_cs_control = nullptr;',s,re.M)
 if not declaration:raise SystemExit('production seed_cs_control declaration not found')
 parts.insert(0,declaration.group(0))
 parts.append(block(s,'CsLayout cs_layout_of('))
parts +=[block(s,'CsLayout cs_layout('),block(s,'uint32_t compute_ssbo_table(')]
head=r'''
#define _CRT_SECURE_NO_WARNINGS
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>
struct NvnState {struct {uint64_t serial=0;unsigned nstage=0;struct {uint64_t control=0;}sd[6];}prog;unsigned cs_push_n=0;};
uint8_t control[216]{};
struct Host {bool gpu_read(uint64_t at,void*out,size_t n){if(at<0x1000||at+n>0x1000+sizeof control)return false;std::memcpy(out,control+at-0x1000,n);return true;}} fake,*host=&fake;
void logf(const char*,...){}
'''
tail=r'''
int main(){
 uint32_t magic=0x98761234;uint16_t stage=5;std::memcpy(control,&magic,4);std::memcpy(control+0x56,&stage,2);
 control[0xb1]=3;control[0xb2]=5;control[0xb3]=2;control[0xb6]=1;control[0xa9]=7;
 NvnState runtime;runtime.prog.serial=8;runtime.prog.nstage=1;runtime.prog.sd[0].control=0x1000;
 uint32_t rc=0,re=0,bc=0,be=0;auto rb=compute_ssbo_table(runtime,&rc,&re);
 if(rb!=0x60||rc!=5||re!=0xc8)return 3;
 NvnState blank;blank.prog.serial=0;
#ifdef FIXED
 seed_cs_control=control;
#endif
 auto bb=compute_ssbo_table(blank,&bc,&be);
 #ifdef FIXED
 seed_cs_control=nullptr;
 #endif
 std::printf("runtime base=%#x count=%u end=%#x; blank preparation base=%#x count=%u end=%#x\n",rb,rc,re,bb,bc,be);
 bool equal=bb==rb&&bc==rc&&be==re;
#ifdef FIXED
 // TLS override is thread-private and bypasses serial0 cached blank state.
 seed_cs_control=control;bool isolated=false;std::thread worker([&]{isolated=seed_cs_control==nullptr;});worker.join();seed_cs_control=nullptr;if(!isolated)return 4;
 uint32_t reset=99;compute_ssbo_table(blank,&reset,nullptr);if(reset!=0)return 5;
#endif
 return equal?0:1;
}
'''
with tempfile.TemporaryDirectory(prefix='prepare-layout-') as tmp:
 folder=Path(tmp);cpp=folder/'check.cpp';exe=folder/'check.exe';cpp.write_text(head+'\n'.join(parts)+tail,encoding='utf-8')
 cmd=[a.cxx,'-std=c++20',str(cpp),'-o',str(exe)]
 if os.name=='nt' and 'clang' in Path(a.cxx).name.lower():cmd+=['--target=x86_64-pc-windows-msvc','-fuse-ld=lld']
 if os.name!='nt':cmd+=['-pthread']
 if a.linker:cmd+=['-B'+str(a.linker.parent)]
 if fixed:cmd+=['-DFIXED']
 subprocess.run(cmd,check=True,timeout=60);r=subprocess.run([str(exe)],timeout=10);raise SystemExit(r.returncode)
