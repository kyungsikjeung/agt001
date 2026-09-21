"""레이어 의존 방향 정적검사. 외부 의존 없음. 위반 1건이면 실패(exit 1)."""
import ast, os, sys

RANK = {"kernel":0,"policy":1,"ports":2,"app":3,"adapters":4,"cli":5}
ALLOW = {          # 상위 -> 참조 허용 하위 집합
 "kernel": set(),
 "policy": {"kernel"},
 "ports":  {"kernel"},
 "app":    {"kernel","policy","ports"},
 "adapters":{"kernel","ports"},
 "cli":    {"kernel","policy","ports","app","adapters"},
}
NET = {"socket","http.client","requests","httpx","urllib.request","aiohttp"}
SOCKET_OWNER = os.path.join("adapters","transport_https.py")

def top(pkg_path):
    parts = pkg_path.replace("\\","/").split("/")
    return parts[0] if parts else ""

def scan(root):
    bad=[]
    for dp,_,fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".py"): continue
            p=os.path.join(dp,fn); rel=os.path.relpath(p,root)
            layer=top(rel)
            if layer not in RANK: continue
            try: tree=ast.parse(open(p,encoding="utf-8").read())
            except SyntaxError as e: bad.append((rel,"파싱실패",str(e))); continue
            for n in ast.walk(tree):
                mods=[]
                if isinstance(n,ast.Import): mods=[a.name for a in n.names]
                elif isinstance(n,ast.ImportFrom) and n.level==0 and n.module: mods=[n.module]
                for m in mods:
                    base=m.split(".")[0]
                    if base in NET and rel!=SOCKET_OWNER:
                        bad.append((rel,"네트워크 라이브러리 반입",m))
                    if base in RANK and base!=layer and base not in ALLOW[layer]:
                        bad.append((rel,"레이어 역방향/금지 참조",m))
                    if layer in ("policy","app") and m.endswith("ports.transport_port") \
                       and not rel.endswith(os.path.join("app","egress_broker.py")):
                        bad.append((rel,"transport_port 직접 참조",m))
    return bad

if __name__=="__main__":
    root=sys.argv[1] if len(sys.argv)>1 else "reqpipe"
    v=scan(root)
    for r in v: print("VIOLATION:", " | ".join(r))
    print(("FAIL %d건"%len(v)) if v else "PASS 위반 0건")
    sys.exit(1 if v else 0)
