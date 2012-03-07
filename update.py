import os
import sys
import json
import shutil
import string
import time
from urllib import quote, unquote

BLACKLIST = [".hg"]
README = "README"
PATHKEYS = "PATHKEYS"
FOLDERS = "FOLDERS"
TESTS = "TESTS"
TESTLISTS = "TESTLISTS"
CHARS = string.ascii_letters + string.digits


class ReadmeContextError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return self.value

class CTX(object):
    def __init__(self, src, target):
        self.src = src
        self.target = target
        self.abs_src = os.path.abspath(src)
        self.abs_target = os.path.abspath(target)
        self.src_path_parts = src.split(os.path.sep)
        self.target_path_parts = target.split(os.path.sep)
        self.dir_list = []
        self.dir_map = {}
        self.components = None

class Folder(object):
    def __init__(self, path):
        self.path = path
        self.dirs = []
        self.labels = []
        self.files = []

    def __repr__(self):
        return str(self.labels) + ", " + str(self.dirs)

class Entry(object):
    def __init__(self):
        self.raw_title = []
        self.raw_url = []
        self.raw_desc = []
        self.raw_label = []
        self.buffer = []
        self.index = 0
        self.mode = ''
        self.tabs = ''
        self.urls = ''
        self.repo = ''
        self.index_count = 0
        self.file_name = ''
        self.deprecated = False
        self._label = None
        self._url = None
        self._desc = None

    def __repr__(self):
        return self.label + ", " + str(self.desc)

    @property
    def label(self):
        if self._label == None:
            self._label = len(self.raw_label) and self.raw_label[0].strip() or ""
        return self._label

    # setter and deleter
    # @label.setter

    @property
    def url(self):
        if self._url == None:
            self._url = len(self.raw_url) and self.raw_url[0].strip() or ""
        return self._url

    @property
    def desc(self):
        if self._desc == None:
            raw_items = self.raw_desc
            string = ""
            items = []
            for item in self.raw_desc:
                if not item.strip():
                    continue
                if item.startswith('-') or item.startswith('*'):
                    if string:
                        items.append(string)
                    string = item.lstrip('-* ')
                else:
                    string += ' ' + item
            if string:
                items.append(string)
            self._desc = items
        return self._desc

def URI_to_system_path(path):
    return path_join(*[unquote(part) for part in path.split("/")])

def parse_readme(path):
    entries = []
    entry = Entry()
    cur = entry.buffer
    counter = 1
    is_pre = False
    pre_sapces = 0
    with open(path, "rb") as in_file:
        for line in in_file.readlines():
            if "@pre" in line:
                pre_sapces = line.find("@pre")
                is_pre = True
                cur.append("@pre")
                continue
            if "@/pre" in line:
                pre_sapces = 0
                is_pre = False
                cur.append("@/pre")
                continue
            if is_pre:
                cur.append(line[pre_sapces:])
                continue
            else:
                line = line.strip()
            if line.startswith('#'):
                continue
            elif not line:
                if entry.raw_label and entry.raw_desc:
                    entries.append(entry)
                entry = Entry()
                cur = entry.buffer
            elif line.startswith('label:'):
                cur = entry.raw_label
                cur.append(line[6:])
            elif line.startswith('desc:'):
                cur = entry.raw_desc
                cur.append(line[5:])
            elif line.startswith('url:'):
                cur = entry.raw_url
                cur.append(line[4:])
            elif line.startswith('***'):
                entry.raw_title = entry.buffer
            elif line.startswith('deprecated:'):
                entry.deprecated = "true" in line.lower() and True or False
            else:
                cur.append(line)

        if entry.label:
            entries.append(entry)
    return entries

def get_tests(ctx, pathkeys, blacklist=[]):
    readme_dirs = set()
    for dirpath, dirs, files in os.walk(ctx.src):
        bl = [d for d in dirs if d in blacklist]
        while bl:
            dirs.pop(dirs.index(bl.pop()))
        abs_path = os.path.abspath(dirpath)
        rel_path = abs_path[len(ctx.abs_src):].lstrip(os.path.sep)
        parts = rel_path.split(os.path.sep)
        path = []
        cur_dir = None
        web_path = ""
        while len(parts):
            part = parts.pop(0)
            path.append(part)
            web_path = "/".join(path)
            if not web_path in  ctx.dir_list:
                ctx.dir_list.append(web_path)
                ctx.dir_map[web_path] = Folder(path)
            cur_dir = ctx.dir_map[web_path]
        if ctx.abs_src == os.path.abspath(dirpath):
            ctx.components = dirs
        if not cur_dir:
            raise ReadmeContextError(dirpath)
        if README in files:
            readme_dirs | set(dirs)
            files.pop(files.index(README))
            entries = parse_readme(os.path.join(dirpath, README))
            if entries:
                paths = ["/".join(path[0:i + 1]) for i in range(len(path))]
                readme_dirs |= set(paths)
            folder_path = ".".join(cur_dir.path)
            for e in entries:
                test_path = cur_dir.path + [e.label.lower().replace(" ", "_")]
                e.short_id = get_short_key(pathkeys, test_path)
                e.file_name = "%s.json" % e.short_id
                e.file_path = "./%s/%s" % (TESTS, e.file_name)
                e.folder_path = folder_path
                cur_dir.labels.append(e)
                if not e.label.strip():
                    print "empty entry"
        cur_dir.dirs = dirs
        cur_dir.files = files
    ctx.readme_dirs = list(readme_dirs)

def get_id(ids):
    cursor = 0
    id = [CHARS[cursor]]
    pos = len(id) - 1
    while "".join(id) in ids:
        cursor += 1
        if cursor >= len(CHARS):
            cursor = 0
            id.append("")
            pos += 1
        id[pos] = CHARS[cursor]
    return "".join(id)

def get_short_key(pathkeys, path):
    short_path = []
    cur = pathkeys
    for p in path:
        if not p in cur:
            short = get_id([cur[k]["short"] for k in cur.keys()])
            print short, cur.keys()
            cur[p] = {"short": short, "dirs": {}}
        short_path.append(cur[p]["short"])
        cur = cur[p]["dirs"]
    return ".".join(short_path)

def create_tests(src, target, ctx):
    tests_path = os.path.join(target, TESTS)
    if not os.path.exists(tests_path):
        os.makedirs(tests_path)
    for d in ctx.dir_map:
        dir_ = ctx.dir_map[d]
        target_path = os.path.join(target, *dir_.path)
        src_path = os.path.join(src, *dir_.path)
        if not os.path.exists(target_path):
            os.makedirs(target_path)
        for e in dir_.labels:
            with open(os.path.join(tests_path, e.file_name), "wb") as f:
                web_path = ["."] + dir_.path[:]
                local_path = e.url.split("/")
                for p in local_path:
                    if p == ".":
                        continue
                    if p == "..":
                        if web_path:
                            web_path.pop()
                    else:
                        web_path.append(p)
                e_dict = {"label": e.label,
                          "url": "/".join(web_path), 
                          "desc": e.desc,
                          "id": e.short_id,
                          "folder_path": e.folder_path}
                f.write(json.dumps(e_dict, indent=4))
        for d in dir_.dirs:
            d_path = os.path.join(target_path, d)
            if not os.path.exists(d_path):
                os.mkdir(d_path)
        for f in dir_.files:
            shutil.copyfile(os.path.join(src_path, f),
                            os.path.join(target_path, f))

def create_folders(src, target, ctx):
    target_path = os.path.join(target, FOLDERS)
    if not os.path.exists(target_path):
        os.makedirs(target_path)
    with open(os.path.join(target_path, "root.json"), "wb") as f:
        dirs = []
        for d in ctx.components:
            dirs.append({"label": d, "path": d})
        f.write(json.dumps({"files": [], "dirs": dirs, "path": ""}, indent=4))
    for p in ctx.readme_dirs:
        name = "%s.json" % p.replace("/", ".")
        folder = ctx.dir_map[p]
        with open(os.path.join(target_path, name), "wb") as f:
            labels = []
            for e in folder.labels:
                labels.append({"label":e.label, "id": e.short_id})
            dirs = []
            folder_path = "%s.%%s" % ".".join(folder.path)
            for d in folder.dirs:
                if "%s/%s" %(p, d) in ctx.readme_dirs:
                    path = folder_path % d
                    dirs.append({"label": d, "path": path})
            f_dict = {"files": labels, "path": p, "dirs": dirs}
            f.write(json.dumps(f_dict, indent=4))

def create_test_lists(src, target, ctx):
    target_path = os.path.join(target, TESTLISTS)
    if not os.path.exists(target_path):
        os.makedirs(target_path)
    for p in ctx.readme_dirs:
        ids = [e.short_id for e in ctx.dir_map[p].labels]
        for p2 in ctx.readme_dirs:
            if not p == p2 and p2.startswith(p):
                ids.extend([e.short_id for e in ctx.dir_map[p2].labels])
        name = "%s.json" % p.replace("/", ".")
        with open(os.path.join(target_path, name), "wb") as f:
            f.write(json.dumps(ids, indent=4))

if __name__ == "__main__":
    argv = sys.argv
    src = "tests"
    target = "suite"
    if len(argv) > 1:
        src = argv[1]
    if len(argv) > 2:
        target = argv[2]
    ctx = CTX(src, target)
    count = 5
    while (count):
        try:
            if os.path.exists(target):
                shutil.rmtree(target)
                break
        except:
            time.sleep(0.2)
        count -= 1
    time.sleep(0.2)
    shutil.copytree(os.path.join("app", "."), os.path.join(target))
    pathkeys = {}
    with open(PATHKEYS, "rb") as f:
        pathkeys = json.loads(f.read())
    get_tests(ctx, pathkeys, BLACKLIST)
    create_tests(src, target, ctx)
    with open(PATHKEYS, "wb") as f:
        f.write(json.dumps(pathkeys, indent=4))
    create_folders(src, target, ctx)
    create_test_lists(src, target, ctx)