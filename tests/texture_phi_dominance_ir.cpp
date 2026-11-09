// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic real TexturePass/Collect/Emit fixture, adapted from depth_sample_types_ir.cpp.
#include <filesystem>
#include <fstream>
#include <unordered_set>
#include "shader_recompiler/backend/spirv/emit_spirv.h"
#include "shader_recompiler/frontend/ir/ir_emitter.h"
#include "shader_recompiler/object_pool.h"
#include "shader_recompiler/environment.h"
#include "shader_recompiler/host_translate_info.h"
#include "shader_recompiler/ir_opt/passes.h"
using namespace Shader;
struct TestEnv : Environment {
 TestEnv(){stage=Stage::Fragment;}
 u64 ReadInstruction(u32)override{return 0;}
 u32 ReadCbufValue(u32,u32)override{return 1;}
 TextureType ReadTextureType(u32)override{return TextureType::Color2D;}
 TexturePixelFormat ReadTexturePixelFormat(u32)override{return {};}
 bool IsTexturePixelFormatInteger(u32)override{return false;}
 u32 ReadViewportTransformState()override{return 1;}
 u32 TextureBoundBuffer()const override{return 0;}
 u32 LocalMemorySize()const override{return 0;}
 u32 SharedMemorySize()const override{return 0;}
 std::array<u32,3> WorkgroupSize()const override{return {1,1,1};}
 bool HasHLEMacroState()const override{return false;}
 std::optional<ReplaceConstant> GetReplaceConstBuffer(u32,u32)override{return {};}
 void Dump(u64,u64)override{}
};
static bool depends(IR::Value value, const IR::Inst* target, std::unordered_set<const IR::Inst*>& seen) {
 const auto* inst=value.TryInstRecursive();
 if(!inst)return false;
 if(inst==target)return true;
 if(!seen.insert(inst).second)return false;
 for(size_t i=0;i<inst->NumArgs();++i)if(depends(inst->Arg(i),target,seen))return true;
 return false;
}
static bool depends(IR::Value value,const IR::Inst* target){std::unordered_set<const IR::Inst*> seen;return depends(value,target,seen);}
static void block_node(IR::Program& p,IR::Block& b){IR::AbstractSyntaxNode n{};n.type=IR::AbstractSyntaxNode::Type::Block;n.data.block=&b;p.syntax_list.push_back(n);}
static IR::U32 offset(IR::IREmitter& ir,u32 word){return ir.ShiftLeftLogical(ir.BitwiseAnd(ir.GetCbuf(ir.Imm32(0u),ir.Imm32(word)),ir.Imm32(3u)),ir.Imm32(3u));}
static void emit(const std::filesystem::path& out,bool diamond){
 ObjectPool<IR::Inst> pool;
 IR::Block entry{pool},body{pool},merge{pool};IR::Program p;p.stage=Stage::Fragment;
 IR::IREmitter a{entry};
 const auto first=offset(a,0x100);
 const auto initial=a.GetCbuf(a.Imm32(0u),a.IAdd(a.Imm32(0x200u),first));
 IR::Value handle=initial;
 IR::Inst* branch_offset=nullptr;
 if(diamond){
  const auto cond=a.ConditionRef(a.INotEqual(a.GetCbuf(a.Imm32(0u),a.Imm32(0x110u)),a.Imm32(0u)));
  entry.AddBranch(&body);entry.AddBranch(&merge);body.AddBranch(&merge);
  IR::IREmitter b{body};const auto second=offset(b,0x108);branch_offset=second.InstRecursive();
  const auto replacement=b.GetCbuf(b.Imm32(0u),b.IAdd(b.Imm32(0x200u),second));
  auto phi=merge.PrependNewInst(merge.begin(),IR::Opcode::Phi);phi->SetFlags(IR::Type::U32);
  phi->AddPhiOperand(&entry,initial);phi->AddPhiOperand(&body,replacement);handle=IR::Value{&*phi};
  if(phi->PhiBlock(0)!=&entry || phi->PhiBlock(1)!=&body || phi->Arg(0)!=initial || phi->Arg(1)!=replacement)throw std::runtime_error("input Phi semantics");
  p.blocks={&entry,&body,&merge};p.post_order_blocks={&merge,&body,&entry};
  block_node(p,entry);IR::AbstractSyntaxNode n{};n.type=IR::AbstractSyntaxNode::Type::If;n.data.if_node={cond,&body,&merge};p.syntax_list.push_back(n);
  block_node(p,body);n={};n.type=IR::AbstractSyntaxNode::Type::EndIf;n.data.end_if.merge=&merge;p.syntax_list.push_back(n);block_node(p,merge);
 }else{p.blocks={&entry};p.post_order_blocks={&entry};block_node(p,entry);}
 IR::IREmitter sample{diamond?merge:entry};IR::TextureInstInfo flags{};flags.type.Assign(TextureType::Color2D);flags.is_depth.Assign(1);
 const auto value=sample.ImageSampleDrefExplicitLod(handle,sample.CompositeConstruct(sample.Imm32(.5f),sample.Imm32(.5f)),sample.Imm32(.5f),sample.Imm32(0.f),IR::Value{},flags);
 auto* instruction=value.InstRecursive();sample.SetFragColor(0,0,value);sample.Epilogue();
 IR::AbstractSyntaxNode ret{};ret.type=IR::AbstractSyntaxNode::Type::Return;p.syntax_list.push_back(ret);
 TestEnv env;HostTranslateInfo host{};host.ApplyDescriptorLimitPolicy();
 Optimization::TexturePass(env,p,host);
 bool unsafe=diamond && depends(instruction->Arg(0),branch_offset);
 // In this triangle the body cannot dominate merge: entry has a direct merge edge.
 // An index Phi is safe; directly following its incoming values as ordinary operands is not.
 if(diamond && instruction->Arg(0).TryInstRecursive() && instruction->Arg(0).InstRecursive()->GetOpcode()==IR::Opcode::Phi)unsafe=false;
 std::printf("%s IR_DOMINANCE=%s incoming-body-index=%d descriptors=%zu\n",diamond?"diamond":"same-block",unsafe?"FAIL":"PASS",diamond?depends(instruction->Arg(0),branch_offset):0,p.info.texture_descriptors.size());
 Optimization::CollectShaderInfoPass(env,p);Profile profile{};profile.supported_spirv=0x00010600;profile.support_int64=true;
 const auto words=Backend::SPIRV::EmitSPIRV(profile,p);
 std::ofstream file(out/(diamond?"diamond.spv":"same-block.spv"),std::ios::binary);file.write(reinterpret_cast<const char*>(words.data()),words.size()*sizeof(u32));if(!file)throw std::runtime_error("write");
}
int main(int argc,char**argv){try{if(argc!=2)return 2;std::filesystem::create_directories(argv[1]);emit(argv[1],false);emit(argv[1],true);return 0;}catch(const std::exception&e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
