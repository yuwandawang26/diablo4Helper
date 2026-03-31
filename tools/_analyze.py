import struct, math
from pathlib import Path

data = Path('d4_candidates.bin').read_bytes()
n = len(data) // 12
print(f'候选总数: {n}')

entries = [(struct.unpack_from('<Qf', data, i*12)) for i in range(n)]

# 找最小地址间距为4（连续float），可能是XYZ三元组
print('\n=== 连续地址组（间距=4，很可能是XYZ三元组）===')
addrs = sorted([a for a,v in entries])
for i in range(len(addrs)-2):
    if addrs[i+1]-addrs[i]==4 and addrs[i+2]-addrs[i+1]==4:
        vals = {a:v for a,v in entries}
        v0 = vals.get(addrs[i],0)
        v1 = vals.get(addrs[i+1],0)
        v2 = vals.get(addrs[i+2],0)
        print(f'  0x{addrs[i]:016X}: [{v0:.4f}, {v1:.4f}, {v2:.4f}]  <- 可能的XYZ')

print('\n=== 单独地址（周围没有其他候选，最像玩家唯一坐标）===')
addr_set = set(addrs)
for a,v in sorted(entries, key=lambda x:x[0]):
    isolated = (a-4 not in addr_set) and (a+4 not in addr_set) and (a-8 not in addr_set) and (a+8 not in addr_set)
    if isolated:
        print(f'  0x{a:016X}: {v:.4f}')
