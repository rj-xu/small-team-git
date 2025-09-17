# noqa: INP001
from enum import StrEnum
from pathlib import Path
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


def is_dirty() -> bool:
    return repo.is_dirty(untracked_files=True)


def count_commits(c0: git.Commit, c1: git.Commit):
    return len(list(repo.iter_commits(f"{c0}..{c1}")))


# def has_conflict(c0: git.Commit, c1: git.Commit) -> bool:
#     return repo.git.merge_tree(c0.name, c1.name, quiet=True) != 0


# def commit_info(c: git.Commit):
#     return f"[ {c.message} ][ {c.author} ][ {c.authored_datetime} ][ {c.hexsha[:8]} ]"


class Cmd(StrEnum):
    # fmt: off
    COMMIT     = "💾 Commit"
    PULL       = "🔽 Pull"
    PUSH       = "🔼 Push"
    RESET      = "🪓 Reset"
    FORCE_PUSH = "⏫ Force-Push"
    SQUASH     = "🧹 Squash"
    ABORT      = "🛑 Abort"
    REBASE     = "🌳 Rebase"
    FETCH      = "🔃 Fetch"
    SYNC       = "🔄️ Sync"
    STASH      = "📁 Stash"
    SUBMOD     = "📦 Submodule"
    # fmt: on

    def start(self):
        typer.echo(f"{self} START")

    def end(self):
        typer.secho(f"{self} END", fg=typer.colors.GREEN)

    def cancel(self):
        typer.secho(f"{self} CANCELLED", fg=typer.colors.YELLOW)

    def fail(self, e: Exception):
        typer.echo(e)
        typer.secho(f"{self} FAILED", fg=typer.colors.RED)

    def info(self, msg: str):
        typer.echo(f"{self} {msg}")

    def warn(self, msg: str):
        typer.secho(f"🚨 {msg}", bg=typer.colors.YELLOW)

    def error(self, msg: str):
        return RuntimeError(f"💥 {msg}")

    def confirm(self, msg: str) -> bool:
        self.warn(msg)
        return typer.confirm("")


@app.command()
def show():
    for cmd in Cmd:
        cmd.start()
        cmd.info("This is Info")
        cmd.warn("This is Warn")
        cmd.cancel()
        cmd.fail(RuntimeError("This is Fail"))
        cmd.end()


@app.command()
def commit(msg: str = "update") -> None:
    if not is_dirty():
        return

    cmd = Cmd.COMMIT
    cmd.start()

    cmd.info(f"Message: {msg}")
    if not repo.index.diff("HEAD"):
        repo.git.add(A=True)
    repo.index.commit(msg)

    cmd.end()


def pull() -> None:
    cmd = Cmd.PULL
    cmd.start()
    origin.pull(rebase=True, autostash=True)
    cmd.end()


def push() -> None:
    cmd = Cmd.PUSH
    cmd.start()
    origin.push(my.name)
    cmd.end()


def reset_to(c: git.Commit, *, need_commit: bool = True) -> None:
    if my.commit == c:
        return

    cmd = Cmd.RESET
    cmd.start()
    repo.git.reset(c)
    cmd.end()

    if need_commit:
        commit(f"reset to {c.hexsha[:8]}")


@app.command()
def reset() -> None:
    base = find_base()
    reset_to(base)
    Cmd.RESET.warn(f"You need to {Cmd.FORCE_PUSH} later")


@app.command()
def force_push() -> bool:
    cmd = Cmd.FORCE_PUSH
    cmd.start()

    try:
        origin.push(my.name, force_with_lease=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        if (
            cmd.confirm("Someone commited into your-origin, OVERWRITE his code?")
            and cmd.confirm("His code may be usefull, continue?")
            and cmd.confirm("Are you sure?")
        ):
            # origin.push(my.name, force=True)
            raise cmd.error("Input: git push --force") from e
        cmd.cancel()
        return False

    cmd.end()
    return True


@app.command()
def squash() -> None:
    cmd = Cmd.SQUASH
    cmd.start()
    base = find_base()
    reset_to(base, need_commit=True)
    force_push()
    cmd.end()


@app.command()
def abort() -> None:
    rebase_merge_dir = Path(repo.git_dir) / "rebase-merge"
    rebase_apply_dir = Path(repo.git_dir) / "rebase-apply"

    in_rebase = rebase_merge_dir.exists() or rebase_apply_dir.exists()

    if not in_rebase:
        return

    cmd = Cmd.ABORT
    cmd.start()

    try:
        repo.git.rebase(abort=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        raise cmd.error("You need to find help") from e

    cmd.end()


def try_rebase(c: git.Commit) -> bool:
    cmd = Cmd.REBASE
    cmd.start()

    try:
        repo.git.rebase(c, autostash=True)
    except git.GitCommandError as e:
        cmd.fail(e)
        return False

    cmd.end()
    return True


def reset_and_rebase(c: git.Commit, base: git.Commit) -> bool:
    cmd = Cmd.REBASE

    if try_rebase(c):
        return True
    abort()

    cmd.warn("Found 💣 Conflict")
    if cmd.confirm(f"{Cmd.RESET} and {Cmd.REBASE} again?"):
        reset_to(base, need_commit=True)
        if not try_rebase(c):
            raise cmd.error(f"You need to resolve conflicts manually, then {Cmd.SYNC}")
        return True
    cmd.cancel()
    return False


def fetch() -> None:
    cmd = Cmd.FETCH
    cmd.start()
    origin.fetch(prune=True, tags=True, prune_tags=True)
    cmd.end()


@app.command()
def sync() -> bool:
    cmd = Cmd.SYNC
    cmd.start()

    fetch()

    base = find_base()
    if base != master.commit:
        cmd.warn("Your branch is out-of-date, need to {Cmd.REBASE} later")

    if my.name not in origin.refs:
        if base == master.commit or reset_and_rebase(master.commit, base):
            push()
        else:
            cmd.cancel()
            raise cmd.error("You need to choose {Cmd.RESET} and {Cmd.REBASE}")
    else:
        my_origin = origin.refs[my.name]

        my_ahead = count_commits(my_origin.commit, my.commit)
        my_origin_ahead = count_commits(my.commit, my_origin.commit)

        if my_ahead > 0 and my_origin_ahead == 0:
            cmd.info(f"{Cmd.PUSH} your branch")
            push()
        elif my_ahead == 0 and my_origin_ahead > 0:
            cmd.info(f"{Cmd.PULL} your-origin branch")
            pull()
        elif my_ahead > 0 and my_origin_ahead > 0:
            cmd.warn("Found 🍴 Fork")

            # NOTE: never rebase others banch
            if (base.committed_datetime > find_base(my_origin, master).committed_datetime) or (
                cmd.confirm(f"{Cmd.PUSH} your branch?")
            ):
                force_push()
            elif (cmd.confirm(f"{Cmd.PULL} your-origin branch?")) and (
                reset_and_rebase(my_origin.commit, find_base(my, my_origin))
            ):
                if my.commit != my_origin.commit:
                    push()
            else:
                cmd.cancel()
                return False
        else:
            cmd.info("Your-origin branch is already up-to-date")

    cmd.end()
    return True


@app.command()
def rebase() -> None:
    if not sync():
        return

    base = find_base()
    if base == master.commit:
        return

    # origin.pull(master.name, rebase=True, autostash=True)
    if reset_and_rebase(master.commit, base):
        force_push()


@app.command()
def stash() -> None:
    stash_cnt = len(cast("str", repo.git.stash("list")).splitlines())
    assert stash_cnt < 2

    cmd = Cmd.STASH
    cmd.start()

    match repo.is_dirty(untracked_files=True), bool(stash_cnt):
        case True, True:
            if cmd.confirm("Do you want to Drop"):
                # repo.git.stash("drop")
                raise cmd.error("Input: git stash drop")
            cmd.cancel()
        case True, False:
            if cmd.confirm("Do you want to Stash?"):
                repo.git.stash("push")
                cmd.end()
            else:
                cmd.cancel()
        case False, True:
            if cmd.confirm("Do you want to Pop?"):
                repo.git.stash("pop")
                cmd.end()
            else:
                cmd.cancel()
        case _:
            raise TypeError


@app.command()
def submod(*, remote: bool = False) -> None:
    if not sync():
        return

    cmd = Cmd.SUBMOD
    cmd.start()
    args = ["update", "--init", "--recursive", "--force"]
    if remote:
        cmd.warn("Update all submodules to remote HEAD")
        args.append("--remote")
    repo.git.submodule(args)
    cmd.end()


@app.command()
def zen() -> None:
    z = [
        "Always keep tree-like structure, linear history",
        "One commit doesn't matter, all commits matter",
        "Only 3 branches: yours, your-origin and master",
        "Take ownership of your branch",
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
