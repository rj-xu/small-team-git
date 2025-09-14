# noqa: INP001
from collections.abc import Callable
from enum import StrEnum
from typing import cast

import git
import typer

app = typer.Typer()


repo = git.Repo(".")
assert repo.index.unmerged_blobs() == {}
# assert repo.git.stash("list") == ""

assert "origin" in repo.remotes
origin = repo.remotes["origin"]

if "master" in origin.refs:
    master = origin.refs["master"]
elif "main" in origin.refs:
    master = origin.refs["main"]
else:
    raise ValueError

my = repo.active_branch
assert my.name not in ("master", "main")

# config_reader = repo.config_reader()
# temp = config_reader.get_value("user", "name", default=None)
# assert isinstance(temp, str)
# user = temp

# temp = config_reader.get_value("user", "email", default=None)
# assert isinstance(temp, str)
# email = temp


def find_base(b0: git.Head = my, b1: git.Head = master):
    bases = repo.merge_base(b0, b1)
    assert len(bases) == 1
    return bases[0]


def has_conflict(c0: git.Commit, c1: git.Commit) -> bool:
    return repo.git.merge_tree(c0.name, c1.name, quiet=True) != 0


def count_commits(c0: git.Commit, c1: git.Commit):
    return len(list(repo.iter_commits(f"{c0}..{c1}")))


def commit_info(c: git.Commit):
    return f"[ {c.message} ][ {c.author} ][ {c.authored_datetime} ][ {c.hexsha[:8]} ]"


@app.command()
def tree():
    pass


@app.command()
def commit(msg: str = "update"):
    if not repo.is_dirty(untracked_files=True):
        return

    typer.echo("💾 Commit START")
    typer.echo(f"💾 Commit Message: {msg}")
    if not repo.index.diff("HEAD"):
        repo.git.add(A=True)
    repo.index.commit(msg)
    typer.echo("💾 Commit END")


def pull():
    typer.echo("🔽 Pull START")
    origin.pull(autostash=True)
    typer.echo("🔽 Pull END")


def push():
    typer.echo("🔼 Push START")
    origin.push(my.name)
    typer.echo("🔼 Push END")


def reset_(c: git.Commit):
    typer.echo("🪓 Reset START")
    repo.git.reset(c)
    typer.echo("🪓 Reset END")


@app.command()
def reset():
    base = find_base()
    reset_(base)


@app.command()
def force_push():
    typer.echo("⏫ Force Push START")
    try:
        origin.push(my.name, force_with_lease=True)
    except git.GitCommandError:
        if (
            typer.confirm("🚨 Someone Push into your-origin, OVERWRITE his code?")
            and typer.confirm("🚨 His code may be usefull, continue?")
            and typer.confirm("🚨 Are you sure?")
        ):
            # origin.push(my.name, force=True)
            typer.echo("🚨 Input this in termial: git push --force")
        else:
            typer.echo("⏫ Push CANCELLED")
    typer.echo("⏫ Force Push END")


def squash_(base: git.Commit, msg: str, *, need_push: bool):
    typer.echo("🧹 Squash START")
    reset_(base)
    commit(msg)
    if need_push:
        force_push()
    typer.echo("🧹 Squash END")


@app.command()
def squash(msg: str = "squash"):
    base = find_base()
    squash_(base, msg=msg, need_push=True)


def try_rebase(autostash: bool):
    try:
        typer.echo("🌳 Rebase START")
        repo.git.rebase(master.commit, autostash=autostash)
        typer.echo("🌳 Rebase END")
    except git.GitCommandError:
        return False
    # force_push()
    return True


def try_pull_rebase(autostash: bool):
    try:
        typer.echo("🌳 Rebase START")
        origin.pull(rebase=True, autostash=autostash)
        typer.echo("🌳 Rebase END")
    except git.GitCommandError:
        return False
    # force_push()
    return True


@app.command()
def abort():
    typer.echo("🛑 Abort Rebase")
    repo.git.rebase(abort=True)


def squash_conflict(rebase_func: Callable[[bool], bool], base: git.Commit):
    squash_(base, "rebase", need_push=False)
    if not rebase_func(False):
        typer.echo("💥 Please resolve Conflict manually, then Sync")
        return False
    return True


def resolve_conflict(func: Callable[[bool], bool], base: git.Commit):
    if not func(True):
        typer.echo("🚨 Found Conflict")
        abort()
        if typer.confirm("🚨 Squash and try again?"):
            return squash_conflict(func, base)
        typer.echo("🚨 CANCELLED")
        return False
    return True


def fetch():
    typer.echo("🌐 Fetch START")
    origin.fetch(prune=True, tags=True, prune_tags=True)
    typer.echo("🌐 Fetch End")


@app.command()
def rebase():
    fetch()

    base = find_base()

    if master.commit == base:
        typer.echo("✅ Already up to date with master")
        return

    rc = resolve_conflict(try_rebase, base)

    if rc:
        force_push()


@app.command()
def sync():
    typer.echo("🔄️ Sync START")

    fetch()

    if my.name not in origin.refs:
        typer.echo("🌳 Rebase START")
        rc = squash_conflict(try_rebase, find_base())
        typer.echo("🌳 Rebase END")
        if rc:
            push()
    else:
        my_origin = origin.refs[my.name]

        if my_origin.commit != my.commit:
            my_ahead = len(list(repo.iter_commits(f"{my_origin.commit}..{my.commit}")))
            my_origin_ahead = len(list(repo.iter_commits(f"{my.commit}..{my_origin.commit}")))

            if my_ahead > 0 and my_origin_ahead == 0:
                typer.echo("🔄️ Sync: Push your commits")
                push()
            elif my_ahead == 0 and my_origin_ahead > 0:
                typer.echo("🔄️ Sync: Pull your-origin commits")
                pull()
            else:
                typer.echo("🚨 Found fork")
                if typer.confirm("🚨 Do you want Pull your-origin code?"):
                    resolve_conflict(try_pull_rebase, find_base(my, my_origin))
                elif typer.confirm("🚨 Do you want to Force-Push your code?"):
                    force_push()
                else:
                    typer.echo("🔄️ Sync CANCELLED")
    typer.echo("🔄️ Sync END")


@app.command()
def stash():
    typer.echo("📁 Stash START")

    stash_cnt = len(cast("str", repo.git.stash("list")).splitlines())
    assert stash_cnt < 2

    match repo.is_dirty(untracked_files=True), bool(stash_cnt):
        case True, True:
            if typer.confirm("🚨 Do you want to Drop"):
                # repo.git.stash("drop")
                typer.echo("🚨 Input this in your termial: git stash drop")
            else:
                typer.echo("📁 Stash CANCELLED")
        case True, False:
            if typer.confirm("📁 Do you want to Stash?"):
                repo.git.stash("push")
            else:
                typer.echo("📁 Stash CANCELLED")
        case False, True:
            if typer.confirm("📁 Do you want to Pop?"):
                repo.git.stash("pop")
            else:
                typer.echo("📁 Stash CANCELLED")
        case _:
            raise TypeError

    typer.echo("📁 Stash END")


@app.command()
def submod():
    pass


if __name__ == "__main__":
    app()
