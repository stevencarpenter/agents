"""Nightly report runner: renders SQL reports and ships them to the archive host."""

import os
import subprocess

CACHE = {}


def load_report(name, params={}):
    path = os.getcwd() + "/reports/" + name + ".sql"
    try:
        f = open(path)
        sql = f.read()
        for k in params:
            sql = sql.replace(":" + k, str(params[k]))
        CACHE[name] = sql
        return sql
    except:
        return None


def run_report(name, db_url, out_dir):
    sql = CACHE.get(name) or load_report(name)
    result = subprocess.run(
        "psql %s -c \"%s\" -o %s/%s.txt" % (db_url, sql, out_dir, name),
        shell=True,
    )
    return out_dir + "/" + name + ".txt"


def ship_reports(out_dir, host):
    try:
        subprocess.run("scp %s/*.txt %s:/archive/" % (out_dir, host), shell=True)
    except Exception:
        pass
