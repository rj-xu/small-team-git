# noqa: INP001
from collections.abc import Callable
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
def commit(msg: str = "update") -> None:
    if not repo.is_dirty(untracked_files=True):
        typer.echo("💾 Commit: there is no changes")
        return

    typer.echo("💾 Commit START")
    typer.echo(f"💾 Commit Message: {msg}")
    if not repo.index.diff("HEAD"):
        repo.git.add(A=True)
    repo.index.commit(msg)
    typer.echo("💾 Commit END")


def pull() -> None:
    typer.echo("🔽 Pull START")
    origin.pull(autostash=True)
    typer.echo("🔽 Pull END")


def push() -> None:
    typer.echo("🔼 Push START")
    origin.push(my.name)
    typer.echo("🔼 Push END")


def reset_commit(c: git.Commit) -> None:
    typer.echo("🪓 Reset START")
    repo.git.reset(c)
    typer.echo("🪓 Reset END")


@app.command()
def reset() -> None:
    base = find_base()
    reset_commit(base)
    typer.echo("🚨 You need to ⏫ Force-Push later")


@app.command()
def force_push() -> bool:
    typer.echo("⏫ Force-Push START")

    try:
        origin.push(my.name, force_with_lease=True)
    except git.GitCommandError:
        typer.echo("🚨 Force-Push FAILED")
        if (
            typer.confirm("🚨 Someone commited into your-origin, OVERWRITE his code?")
            and typer.confirm("🚨 His code may be usefull, continue?")
            and typer.confirm("🚨 Are you sure?")
        ):
            # origin.push(my.name, force=True)
            raise RuntimeError("💥 Input this in termial: git push --force")
        else:
            typer.echo("⏫ Force-Push CANCELLED")

    typer.echo("⏫ Force-Push END")
    return True


def squash_commit(base: git.Commit, msg: str) -> None:
    typer.echo("🧹 Squash START")
    reset_commit(base)
    commit(msg)
    typer.echo("🧹 Squash END")


@app.command()
def squash(msg: str = "squash") -> None:
    base = find_base()
    squash_commit(base, msg=msg)
    force_push()


@app.command()
def abort() -> None:
    typer.echo("🛑 Abort-Rebase")
    try:
        repo.git.rebase(abort=True)
    except git.GitCommandError:
        raise RuntimeError("💥 Abort-Rebase FAILED, please find help")


def rebase_commit(c: git.Commit) -> bool:
    typer.echo("🌳 Rebase START")

    try:
        repo.git.rebase(c, autostash=True)
    except git.GitCommandError:
        typer.echo("🚨 Rebase FAILED")
        abort()
        return False

    typer.echo("🌳 Rebase END")
    return True


def pull_rebase() -> bool:
    typer.echo("🌳 Pull-Rebase START")

    try:
        origin.pull(rebase=True, autostash=True)
    except git.GitCommandError:
        typer.echo("🚨 Pull-Rebase FAILED")
        abort()
        return False

    typer.echo("🌳 Pull-Rebase END")
    return True


def squash_then_rebase(c: git.Commit, base: git.Commit) -> bool:
    squash_commit(base, "rebase")
    if not rebase_commit(c):
        raise RuntimeError("💥 Please resolve Conflict manually, then 🔄️ Sync")

    typer.echo("🌳 Rebase END")
    return True


def try_rebase(c: git.Commit, base: git.Commit) -> bool:
    if not rebase_commit(c):
        typer.echo("🚨 Found Conflict")
        if typer.confirm("🚨 Squash and try again?"):
            return squash_then_rebase(c, base)
        typer.echo("🌳 Rebase CANCELLED")
        return False

    typer.echo("🌳 Rebase END")
    return True


def fetch() -> None:
    typer.echo("🔃 Fetch START")
    origin.fetch(prune=True, tags=True, prune_tags=True)
    typer.echo("🔃 Fetch End")


@app.command()
def sync() -> bool:
    typer.echo("🔄️ Sync START")

    fetch()

    base = find_base()
    if base != master.commit:
        typer.echo("🚨 You are not up to date with master, please 🌳 Rebase later")

    if my.name not in origin.refs:
        if (base == master.commit) or (base == my.commit and rebase_commit(base)) or squash_then_rebase(base, base):
            push()
        else:
            typer.echo("💥 Unreachable")
            raise RuntimeError
    else:
        my_origin = origin.refs[my.name]

        my_ahead = len(list(repo.iter_commits(f"{my_origin.commit}..{my.commit}")))
        my_origin_ahead = len(list(repo.iter_commits(f"{my.commit}..{my_origin.commit}")))

        if my_ahead > 0 and my_origin_ahead == 0:
            typer.echo("🔄️ Sync: Push your commits")
            push()
        elif my_ahead == 0 and my_origin_ahead > 0:
            typer.echo("🔄️ Sync: Pull your-origin commits")
            pull()
        elif my_ahead > 0 and my_origin_ahead > 0:
            typer.echo("🚨 Found Fork")
            my_origin_base = find_base(my_origin, master)

            # NOTE: never rebase others banch or commit when other is rebasing

            if base.committed_datetime > my_origin_base.committed_datetime:
                force_push()
            elif typer.confirm("🚨 Keep your-origin code?"):
                try_rebase(my_origin.commit, find_base(my, my_origin))
            elif typer.confirm("🚨 Keep your code?"):
                force_push()
            else:
                typer.echo("🔄️ Sync CANCELLED")
                return False
        else:
            typer.echo("🔄️ Sync: your-orgin is up to date with your-local")

    typer.echo("🔄️ Sync END")
    return True


@app.command()
def rebase() -> None:
    # origin.pull(master.name, rebase=True, autostash=True)

    if not sync():
        typer.echo("🌳 Rebase CANCELLED")
        return

    base = find_base()
    if base == master.commit:
        typer.echo("✅ Already up to date with master")
        return
    rc = try_rebase(rebase_master, base)
    if rc:
        force_push()


@app.command()
def stash() -> None:
    typer.echo("📁 Stash START")

    stash_cnt = len(cast("str", repo.git.stash("list")).splitlines())
    assert stash_cnt < 2

    match repo.is_dirty(untracked_files=True), bool(stash_cnt):
        case True, True:
            if typer.confirm("🚨 Do you want to Drop"):
                # repo.git.stash("drop")
                raise RuntimeError("💥 Input this in your termial: git stash drop")
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
def submod(use_latest: bool = False) -> None:
    typer.echo("📦 Submodule-Update START")
    args = ["update", "--init", "--recursive", "--force"]
    if use_latest:
        args.append("--remote")
    repo.git.submodule(args)
    typer.echo("📦 Submodule-Update END")


@app.command()
def zen() -> None:
    z = [
        "Always keep the tree structure, linear history",
        "A commit doesn't matter, the total amount of commits matters",
        "Only three branches, yours, your origin, master",
        "Be responsible for your own branch",
        r"         ",
        r"    |    ",
        r"    ●    ",
        r" |  |    ",
        r" ●  ●    ",
        r"  \ |  | ",
        r"    ●  ● ",
        r"    | /  ",
        r"    ●    ",
        r"    |    ",
        r"         ",
    ]
    for line in z:
        typer.echo(line)


if __name__ == "__main__":
    app()
