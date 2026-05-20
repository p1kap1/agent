# 2026-05-20 开发记录

## 新增功能
- boss.py: Boss直聘4模块数据抓取（沟通过/已投递/面试/感兴趣），支持多API端点切换
- 自动翻页获取全量数据（突破服务端15条/页限制），按happenTime自动计算日期分布
- Excel导出双区域格式（上方3模块+下方面试专区），日期筛选+序号防重
- skills.py: 新增fetch_boss_channels/applied/interviews/interested、boss_job_summary、export_boss_excel、list_exported_files
- git_ops.py: Git推送模块，add+commit+push一键完成，认证失败自动提示
- git_push_project、git_display_status、generate_project_summary、import_devlog 技能
- users.json: 多用户Cookie配置支持
- chainlit_app.py: 技能调用详情调试面板

## 修复的问题
- skills.py: return(...)缺少右括号导致SyntaxError
- _import_boss()使用importlib绝对路径加载，修复Chainlit环境下sys.path不包含项目目录导致的ModuleNotFoundError
- execute_skill过滤AI编造的无关参数（如boss_token），防止TypeError
- 已投递接口tag=3被拒，改用/wapi/zprelation/resume/geekDeliverList
- 面试接口改用/wapi/zpinterview/geek/interview/list，解析interviewList+面试特有字段
- 企业链接和企业名列合并，去除冗余列
- 去重逻辑同时检查encrypt_job_id和job_id

## 遇到的技术难点
- Boss直聘API分页限制：服务端最多返回15条，需循环翻页直到hasMore=false
- 沟通过/感兴趣API只支持tag=2/4/5，tag=3返回“未知的非法参数”
- 面试数据是系统推荐(hasContact=0)而非真实面试邀请，需通过用户抓包拿到真实接口
- Python 3.14 + nest_asyncio兼容性：current_task()返回None导致anyio崩溃，需5层monkey-patch
- Chainlit环境sys.path不含项目目录，import boss失败，需importlib手动加载
- DeepSeek会编造不存在的参数名，需execute_skill过滤
- Classic PAT才能push代码，fine-grained PAT需额外配置Contents权限

## 解决方案
- 循环翻页：while hasMore: page+=1, sleep(0.3)
- 已投递/面试换用独立接口，分别对接geekDeliverList和interview/list
- Python 3.14补丁：patch _run_once存task到thread-local，patch current_task/asyncio.timeout/CancelScope
- importlib.util动态加载模块，绕过sys.path问题
- execute_skill用inspect.signature过滤参数
- 经典PAT(ghp_)配置Remote URL，完成推送
- devlog.md机制：开发对话摘要写入文件，Agent通过import_devlog读取后参与项目总结
