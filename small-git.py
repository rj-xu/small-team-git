# noqa: INP001
import os
from typing import Annotated

import git
import typer

app = typer.Typer()


repo = git.Repo(".")
assert repo.index.unmerged_blobs() == {}
# assert repo.git.stash("list") == ""


config_reader = repo.config_reader()
temp = config_reader.get_value("user", "name", default=None)
assert isinstance(temp, str)
user = temp

temp = config_reader.get_value("user", "email", default=None)
assert isinstance(temp, str)
email = temp

assert "origin" in repo.remotes
origin = repo.remotes["origin"]

if "master" in origin.refs:
    master = origin.refs["master"]
elif "main" in origin.refs:
    master = origin.refs["main"]
else:
    raise ValueError("No master or main branch found")

my = repo.active_branch
assert my.name not in ("master", "main")


def find_base(b: git.Head = my):
    bases = repo.merge_base(b, master)
    assert len(bases) == 1
    return bases[0]


base: git.Commit = find_base()


def find_latest_mr():
    return master.commit


def find_my_mr():
    base_time = base.committed_datetime
    for commit in repo.iter_commits(master):
        if commit.committed_datetime <= base_time:
            break
        if commit.author.email and email in commit.author.email:
            return commit
    return None


def is_conflict(b0: git.Head = my, b1: git.Head = master):
    return repo.git.merge_tree(b0.name, b1.name, quiet=True) != 0


def commit_info(c: git.Commit):
    return f"[ {c.message} ][ {c.author} ][ {c.authored_datetime} ][ {c.hexsha[:8]} ]"


@app.command()
def fetch():
    typer.echo("☁️ Fetch START")
    origin.fetch(prune=True, tags=True, prune_tags=True)
    typer.echo("☁️ Fetch End")


@app.command()
def commit(msg: str = "update"):
    typer.echo("💾 Commit START")
    typer.echo(f"💾 Commit Message: {msg}")
    repo.git.add(A=True)
    repo.index.commit(msg)
    typer.echo("💾 Commit END")


@app.command()
def pull():
    typer.echo(f"⏬ Pull START")
    origin.pull(rebase=True, autostash=True)
    typer.echo(f"⏬ Pull End")


@app.command()
def force_push(force_with_lease: bool = True, force: bool = False):
    match force_with_lease, force:
        case True, False:
            s = "-Force-With-Lease"
        case False, True:
            s = "-Force"
        case False, False:
            s = ""
        case _:
            raise ValueError

    typer.echo(f"⏫ Push{s} START")
    origin.push(my.name, force_with_lease=force_with_lease)
    typer.echo(f"⏫ Push{s} End")


@app.command()
def sync():
    typer.echo("🔄️ Sync START")

    fetch()

    if my.name not in origin.refs:
        typer.echo("🔄️ Sync: Publish your branch")
        force_push(False, False)
    else:
        my_origin = origin.refs[my.name]

        if my_origin.commit != my.commit:
            my_ahead = len(list(repo.iter_commits(f"{my_origin.commit}..{my.commit}")))
            my_origin_ahead = len(list(repo.iter_commits(f"{my.commit}..{my_origin.commit}")))

            if my_ahead > 0 and my_origin_ahead == 0:
                typer.echo("🔄️ Sync: Push your commits")
                force_push(False, False)
            elif my_ahead == 0 and my_origin_ahead > 0:
                typer.echo("🔄️ Sync: Pull your-origin commits")
                origin.pull(rebase=True, autostash=True)
            else:
                typer.echo("🔄️ Sync: Found Fork")
                try:
                    force_push(False, False)
                except git.GitCommandError as e:
                    typer.echo(f"⚠️ Sync: Failed to Force-Push: {e}")

                    if typer.confirm("⚠️ Sync: Maybe someone push into your-origin branch, OVERWRITE his code?"):
                        force_push(force=True)
                    elif typer.confirm("⚠️ Sync: OVERWRITE your code?"):
                        pull()
                        force_push(False, False)
                    else:
                        typer.echo("🔄️ Sync STOP")

    typer.echo("🔄️ Sync END")


@app.command()
def squash(push: bool = True):
    typer.echo("🧹 Squash START")
    repo.git.reset(base)
    if push:
        force_push()
    typer.echo("🧹 Squash END")


@app.command()
def reset(push: bool = True):
    global base

    fetch()

    my_mr = find_my_mr()
    if my_mr:
        typer.echo("🪓 Reset START")
        typer.echo(f"🪓 Reset: {commit_info(my_mr)}")
        if typer.confirm("🪓 Reset: Is this your latest Merge-Request?"):
            repo.git.reset(my_mr)
            base = my_mr
            if push:
                force_push()
        else:
            typer.echo("🪓 Reset STOP")
        typer.echo("🪓 Reset END")


@app.command()
def rebase():
    fetch()

    base = find_base()

    if master.commit == base:
        return

    try:
        typer.echo("🌳 Rebase START")
        repo.git.rebase(master.commit, autostash=True)
    except git.GitCommandError:
        repo.git.rebase(abort=True)
        repo.git.reset(base)
        repo.git.rebase(master.commit, autostash=True)



    master_mr = find_latest_mr()
    if master_mr.committed_datetime > base.committed_datetime:
        typer.echo("🌳 Rebase START")
        if is_conflict():
            # if typer.echo("💥 Conflict: Suggest you to Squash to ?")
            if not typer.confirm("💥 Conflict: You need to resolve manually, then force-push, continue?"):
                typer.echo("🛑 Abort START")
                repo.git.rebase(abort=True)
                typer.echo("🛑 Abort END")
                return

            repo.git.reset(base)
        typer.echo("🌳 Rebase: Latest Master Merge-Request is {master_mr}")
        repo.git.rebase(master_mr, autostash=True)

        typer.echo("🌳 Rebase END")
    force_push()


@app.command()
def abort():
    typer.echo("🛑 Abort START")
    repo.git.rebase(abort=True)
    typer.echo("🛑 Abort END")


# @app.command()
# def auto():
#     typer.echo("🤖 Auto Small-Git...")
#     sync()
#     need_push = False
#     need_push |= reset(False)
#     need_push |= rebase(False)
#     if need_push:
#         force_push()
#     submod()
#     os.system("uv sync")
#     typer.echo("✅ DONE")


def iter_commits(c1: git.Commit, c0: git.Commit):
    return repo.iter_commits(f"{c0}..{c1}")


def has_conflict(c0: git.Commit, c1: git.Commit) -> bool:
    return repo.git.merge_tree(c0.name, c1.name, quiet=True) != 0


@app.command()
def auto():
    assert repo.is_dirty()

    fetch()

    base = find_base()
    master_mr = find_latest_mr()

    if master_mr == base:
        return

    found_new_base = False
    found_conflict = False
    need_use_onto = False

    for my_i in iter_commits(my.commit, base):
        for master_i in iter_commits(master.commit, base):
            if not has_conflict(my_i, master_i):
                found_new_base = True
                found_conflict = master_i != master.commit
                need_use_onto = my_i != my.commit

    if found_new_base:
        reset()




@app.command()
def stash():
    typer.echo("🗄️ Stash START")
    if repo.git.stash("list"):
        if typer.confirm("🗄️ Do you want to pop the stash?"):
            repo.git.stash("pop")
        else:
            typer.echo("🗄️ Stash STOP")
    elif repo.is_dirty():
        if typer.confirm("🗄️ Do you want to stash the changes?"):
            repo.git.stash()
        else:
            typer.echo("🗄️ Stash STOP")
    else:
        typer.echo("🗄️ Stash STOP")
    typer.echo("🗄️ Stash STOP")


@app.command()
def submod(
    remote: Annotated[bool, typer.Option(prompt="🤖 update to remote latest (NOT follow repo)")] = False,
):
    typer.echo("📦 Submodule START")
    args = ["update", "--init", "--recursive", "--force"]
    if remote:
        args.append("--remote")
    repo.git.submodule(args)
    typer.echo("📦 Submodule END")


if __name__ == "__main__":
    app()
