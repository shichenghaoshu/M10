#include <rknn_api.h>
#include <ssd.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <vector>

static std::vector<unsigned char> read_file(const char* filename);
static uint32_t little_u32(const unsigned char* p) { return uint32_t(p[0])|(uint32_t(p[1])<<8U)|(uint32_t(p[2])<<16U)|(uint32_t(p[3])<<24U); }
static int32_t little_i32(const unsigned char* p) { return static_cast<int32_t>(little_u32(p)); }
static std::vector<unsigned char> read_bmp_rgb(const char* filename, int expected_w, int expected_h) {
  auto file=read_file(filename); if(file.size()<54||file[0]!='B'||file[1]!='M')return {};
  const uint32_t offset=little_u32(file.data()+10),w=little_u32(file.data()+18); const int32_t signed_h=little_i32(file.data()+22);
  const uint32_t h=static_cast<uint32_t>(signed_h<0?-static_cast<int64_t>(signed_h):signed_h); const bool top_down=signed_h<0;
  if(w!=static_cast<uint32_t>(expected_w)||h!=static_cast<uint32_t>(expected_h)||file[28]!=24)return {};
  const size_t stride=(w*3U+3U)&~3U; if(offset+stride*h>file.size())return {};
  std::vector<unsigned char> rgb(w*h*3U);
  for(uint32_t y=0;y<h;y++)for(uint32_t x=0;x<w;x++){
    const uint32_t source_y=top_down?y:(h-1U-y); const auto* source=file.data()+offset+source_y*stride+x*3U; auto* dest=rgb.data()+(y*w+x)*3U;
    dest[0]=source[2];dest[1]=source[1];dest[2]=source[0];
  }
  return rgb;
}

static std::vector<unsigned char> read_file(const char* filename) {
  std::ifstream input(filename, std::ios::binary | std::ios::ate);
  if (!input) return {};
  const auto size = input.tellg(); input.seekg(0);
  std::vector<unsigned char> data(static_cast<size_t>(size)); input.read(reinterpret_cast<char*>(data.data()), size);
  return data;
}

static void print_tensor(const char* side, const rknn_tensor_attr& a) {
  std::printf("%s[%u] name=%s dims=", side, a.index, a.name);
  for (uint32_t i=0;i<a.n_dims;i++) std::printf("%u%s", a.dims[i], i+1==a.n_dims?"":"x");
  std::printf(" elems=%u size=%u fmt=%d type=%d qnt=%d zp=%d scale=%g\n", a.n_elems,a.size,a.fmt,a.type,a.qnt_type,a.zp,a.scale);
}

int main(int argc, char** argv) {
  if (argc < 2 || argc > 4) { std::fprintf(stderr,"usage: %s model.rknn [300x300.bmp] [iterations]\n",argv[0]); return 2; }
  const int iterations=argc>=4?std::max(1,std::atoi(argv[3])):1;
  auto model=read_file(argv[1]); if(model.empty()){std::fprintf(stderr,"MODEL_READ_FAILED path=%s\n",argv[1]);return 3;}
  rknn_context ctx=0; int rc=rknn_init(&ctx,model.data(),model.size(),0,nullptr);
  if(rc<0){std::fprintf(stderr,"NPU_INIT_FAILED rc=%d\n",rc);return 4;}
  rknn_sdk_version version{}; rc=rknn_query(ctx,RKNN_QUERY_SDK_VERSION,&version,sizeof(version));
  if(rc==RKNN_SUCC) std::printf("SDK api=%s driver=%s\n",version.api_version,version.drv_version);
  rknn_input_output_num count{}; rc=rknn_query(ctx,RKNN_QUERY_IN_OUT_NUM,&count,sizeof(count));
  if(rc!=RKNN_SUCC){std::fprintf(stderr,"QUERY_IO_FAILED rc=%d\n",rc);rknn_destroy(ctx);return 5;}
  std::printf("MODEL bytes=%zu inputs=%u outputs=%u\n",model.size(),count.n_input,count.n_output);
  std::vector<rknn_tensor_attr> inputs(count.n_input),outputs(count.n_output);
  for(uint32_t i=0;i<count.n_input;i++){inputs[i].index=i;rc=rknn_query(ctx,RKNN_QUERY_INPUT_ATTR,&inputs[i],sizeof(inputs[i]));if(rc<0)return 6;print_tensor("input",inputs[i]);}
  for(uint32_t i=0;i<count.n_output;i++){outputs[i].index=i;rc=rknn_query(ctx,RKNN_QUERY_OUTPUT_ATTR,&outputs[i],sizeof(outputs[i]));if(rc<0)return 7;print_tensor("output",outputs[i]);}
  std::vector<std::vector<unsigned char>> buffers(count.n_input); std::vector<rknn_input> set_inputs(count.n_input);
  for(uint32_t i=0;i<count.n_input;i++){buffers[i].assign(inputs[i].size,0);set_inputs[i].index=i;set_inputs[i].buf=buffers[i].data();set_inputs[i].size=inputs[i].size;set_inputs[i].type=RKNN_TENSOR_UINT8;set_inputs[i].fmt=RKNN_TENSOR_NHWC;}
  if(argc>=3){auto pixels=read_bmp_rgb(argv[2],300,300);if(pixels.size()!=buffers[0].size()){std::fprintf(stderr,"IMAGE_READ_FAILED path=%s\n",argv[2]);rknn_destroy(ctx);return 11;}buffers[0]=std::move(pixels);set_inputs[0].buf=buffers[0].data();std::printf("IMAGE_RGB_OK path=%s bytes=%zu\n",argv[2],buffers[0].size());}
  rc=rknn_inputs_set(ctx,count.n_input,set_inputs.data());if(rc<0){std::fprintf(stderr,"INPUT_SET_FAILED rc=%d\n",rc);rknn_destroy(ctx);return 8;}
  std::vector<double> timings;timings.reserve(iterations);
  for(int iteration=0;iteration<iterations;iteration++){const auto start=std::chrono::steady_clock::now();rc=rknn_run(ctx,nullptr);const auto end=std::chrono::steady_clock::now();
    if(rc<0){std::fprintf(stderr,"NPU_RUN_FAILED iteration=%d rc=%d\n",iteration,rc);rknn_destroy(ctx);return 9;}timings.push_back(std::chrono::duration<double,std::milli>(end-start).count());}
  std::vector<rknn_output> got(count.n_output);for(auto& output:got)output.want_float=1;
  rc=rknn_outputs_get(ctx,count.n_output,got.data(),nullptr);if(rc<0){std::fprintf(stderr,"OUTPUT_GET_FAILED rc=%d\n",rc);rknn_destroy(ctx);return 10;}
  auto sorted=timings;std::sort(sorted.begin(),sorted.end());double sum=0;for(double value:timings)sum+=value;
  const double p50=sorted[sorted.size()/2],p95=sorted[std::min(sorted.size()-1,static_cast<size_t>(sorted.size()*0.95))];
  std::printf("NPU_RUN_OK iterations=%d avg_ms=%.3f p50_ms=%.3f p95_ms=%.3f fps=%.3f outputs=%u\n",iterations,sum/iterations,p50,p95,1000.0/(sum/iterations),count.n_output);
  if(count.n_output==2&&got[0].buf&&got[1].buf){detect_result_group_t group{};postProcessSSD(static_cast<float*>(got[0].buf),static_cast<float*>(got[1].buf),300,300,&group);std::printf("DETECTIONS count=%d\n",group.count);for(int i=0;i<group.count;i++)std::printf("DETECTION class=%s confidence=%.4f box=%d,%d,%d,%d\n",group.results[i].name,group.results[i].prop,group.results[i].box.left,group.results[i].box.top,group.results[i].box.right,group.results[i].box.bottom);}
  rknn_outputs_release(ctx,count.n_output,got.data());rknn_destroy(ctx);return 0;
}
