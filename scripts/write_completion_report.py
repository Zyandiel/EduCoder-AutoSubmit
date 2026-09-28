"""根据实际读取的关卡状态与本地解答生成完成记录，不改变网站状态。"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from educoder.solution_files import load_files
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'logs/catalog.json').read_text(encoding='utf-8'))
records=[]
for assignment in catalog:
    challenges=assignment.get('challenges',[])
    if not challenges or any(c['passed'] is not True for c in challenges):
        raise ValueError('存在未确认通过的作业：'+assignment['assignment'])
    for challenge in challenges:
        solution=root/'solutions'/assignment['assignment']/f"{challenge['number']}.cpp"
        files=[]
        for remote,path in load_files(solution):
            files.append({'remote':remote,'local':str(path.relative_to(root)),
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        records.append({'assignment':assignment['assignment'],'number':challenge['number'],
                        'title':challenge['name'],'passed':True,'files':files})
now=datetime.now().astimezone().isoformat(timespec='seconds')
report={'verified_at':now,'assignment_count':len(catalog),'challenge_count':len(records),
        'final_submission':False,'records':records}
(root/'logs/completion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# 关卡评测完成记录','',f'核对时间：{now}',
       f'','当前范围：{0}个实训、{1}关，均已通过。'.format(len(catalog),len(records)),
       '保持 `dry_run: true`，没有执行最终提交或提交总结。','',
       '| 实训 | 已通过 |','|---|---|']
lines += [f"| {a['assignment']} | {len(a['challenges'])}/{len(a['challenges'])} |" for a in catalog]
lines += ['', '代码位于 `solutions/<实训名称>/<关卡号>.cpp`。多文件关卡通过同名 `.files.json` 指定网页文件映射。',
          '本地辅助头文件只用于编译检查；仅映射文件会写入平台。部分解答是头文件或函数实现，需要平台提供的主程序，不能单独链接运行。',
          '', '证据：`logs/catalog.json`（逐关状态）、`logs/completion.json`（本地文件与 SHA-256）、`logs/guided-*/report.json`（逐关评测）。',
          '历史失败和中断日志保留，最终状态以最新核对结果为准。']
(root/'COMPLETION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'CONFIRMED {len(catalog)} assignments / {len(records)} challenges')
