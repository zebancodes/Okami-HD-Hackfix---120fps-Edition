import pickle, struct, bisect, collections
c = pickle.load(open("tools/.disasm_cache/read_candidates.pkl", "rb"))
img = c["img"]; ins = c["insns"]; addrs = [i[0] for i in ins]
def first_call(a):
    j = bisect.bisect_left(addrs, a)
    for k in range(j, j + 6):
        ad, m, o, s = ins[k]
        if m == "call" and o.startswith("0x"):
            return int(o, 16) - 0x180000000
        if m in ("jmp", "ret"):
            return None
    return None
A = collections.defaultdict(list); B = collections.defaultdict(list)
for st in range(0x5F):
    idx = img[0x3AF840 + st]
    t = struct.unpack_from("<I", img, 0x3AF79C + 4 * idx)[0]
    f = first_call(t)
    A[f].append(st)
    t2 = struct.unpack_from("<I", img, 0x3AF8A0 + 4 * st)[0]
    f2 = first_call(t2)
    B[f2].append(st)
print("first switch (3AF106):")
for f, sts in sorted(A.items(), key=lambda kv: kv[1][0]):
    print("  %s: %s" % ("%X" % f if f else "-", " ".join("%02X" % s for s in sts)))
print("second switch (3AF3F8):")
for f, sts in sorted(B.items(), key=lambda kv: kv[1][0]):
    print("  %s: %s" % ("%X" % f if f else "-", " ".join("%02X" % s for s in sts)))
