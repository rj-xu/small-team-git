# noqa: INP001
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Annotated

import git
import rich
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


def find_latest_master_mr():
    return master.commit


def find_my_mr():
    base_time = base.committed_datetime
    for commit in repo.iter_commits(master):
        if commit.committed_datetime <= base_time:
            return None

        if commit.author.email and email.lower() in commit.author.email.lower():
            return commit
    return None


def is_conflict(current: git.Head = my, target: git.Head = master):
    result = repo.git.merge_tree(current.name, target.name)
    return "CONFLICT" in result


def my_commits_num() -> int:
    commits = list(repo.iter_commits(f"{base}..{my.commit}"))
    return len(commits)


def commit_info(c: git.Commit) -> str:
    return f"[ {c.message} ][ {c.author} ][ {c.authored_datetime} ][ {c.hexsha[:8]} ]"


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
    remote: Annotated[
        bool, typer.Option(prompt="🤖 update to remote latest (NOT follow repo)")
    ] = False,
):
    typer.echo("📦 Submodule START")
    args = ["update", "--init", "--recursive", "--force"]
    if remote:
        args.append("--remote")
    repo.git.submodule(args)
    typer.echo("📦 Submodule END")


@app.command()
def abort():
    typer.echo("🛑 Abort START")

    if repo.is_dirty(untracked_files=False):
        if repo.index.unmerged_blobs():
            typer.echo("🔄️ Detected merge conflict, aborting merge")
            repo.git.merge("--abort")
            return

    git_dir = Path(repo.git_dir)

    if (git_dir / "MERGE_HEAD").exists():
        typer.echo("🔄️ Detected ongoing merge, aborting")
        repo.git.merge("--abort")

    elif (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        typer.echo("🌳 Detected ongoing rebase, aborting")
        repo.git.rebase("--abort")

    elif (git_dir / "CHERRY_PICK_HEAD").exists():
        typer.echo("🍒 Detected ongoing cherry-pick, aborting")
        repo.git.cherry_pick("--abort")

    elif (git_dir / "REVERT_HEAD").exists():
        typer.echo("↩️ Detected ongoing revert, aborting")
        repo.git.revert("--abort")

    else:
        typer.echo("❌ No ongoing Git operation detected")

    typer.echo("🛑 Abort END")


def drop():
    pass


def tree():
    pass


@app.command()
def commit(
    msg: Annotated[str, typer.Option(prompt="🤖 Input Commit Message")] = "update",
):
    typer.echo("💾 Commit START")
    typer.echo(f"💾 Commit Message: {msg}")
    repo.git.add(A=True)
    repo.index.commit(msg)
    typer.echo("💾 Commit END")


@app.command()
def force_push():
    typer.echo("⏫ Force-Push START")
    origin.push(my.name, force_with_lease=True)
    typer.echo("⏫ Force-Push End")


@app.command()
def sync():
    typer.echo("🔄️ Sync START")

    origin.fetch(prune=True, tags=True, prune_tags=True)

    if my.name not in origin.refs:
        typer.echo("🔄️ Sync: Publish your branch")
        origin.push(my.name)
    else:
        my_origin = origin.refs[my.name]

        if my_origin.commit != my.commit:
            my_ahead = len(list(repo.iter_commits(f"{my_origin.commit}..{my.commit}")))
            my_origin_ahead = len(
                list(repo.iter_commits(f"{my.commit}..{my_origin.commit}"))
            )

            if my_ahead > 0 and my_origin_ahead == 0:
                typer.echo("🔄️ Sync: Push your commits")
                origin.push(my.name)
            elif my_ahead == 0 and my_origin_ahead > 0:
                typer.echo("🔄️ Sync: Pull origin commits")
                origin.pull(rebase=True, autostash=True)
            else:
                typer.echo("🔄️ Sync: Found Fork")
                try:
                    force_push()
                except git.GitCommandError as e:
                    typer.echo(f"⚠️ Sync: Failed to push: {e}")

                    if typer.confirm(
                        "⚠️ Sync: Maybe someone push code into your branch, OVERWRITE his code?"
                    ):
                        origin.push(my.name, force=True)
                    elif typer.confirm("⚠️ Sync: OVERWRITE yours code?"):
                        origin.pull(rebase=True, autostash=True)
                        origin.push(my.name)
                    else:
                        typer.echo("🔄️ Sync STOP")

    typer.echo("🔄️ Sync END")


def merge():
    typer.echo("📋 Merge Request START")
    if repo.is_dirty():
        typer.echo(
            "❌ Working directory is dirty. Please commit or stash changes first."
        )
        return
    sync()
    tag_name = f"{user}-MergeRequest"
    if tag_name in [tag.name for tag in repo.tags]:
        typer.echo("⚠️ Merge Request: Tag already exists")
        return False
    repo.git.tag("-a", tag_name, "-m", f"Merge Request from {user}")
    typer.echo(f"🏷️ Created tag {tag_name}")
    origin.push(tag_name)


def tag():
    typer.echo("🏷️ Tag START")

    try:
        date_str = datetime.now().strftime("%Y%m%d")
        random_num = random.randint(100, 999)  # 生成三位随机数
        tag_name = f"{user}-{date_str}-{random_num}"

        # 检查标签是否已存在
        existing_tags = [tag.name for tag in repo.tags]
        if tag_name in existing_tags:
            # 如果标签已存在，生成新的随机数
            for _ in range(10):  # 最多尝试10次
                random_num = random.randint(100, 999)
                tag_name = f"{user}-{date_str}-{random_num}"
                if tag_name not in existing_tags:
                    break
            else:
                typer.echo("❌ Could not generate unique tag name after 10 attempts")
                return False

        # 创建带注释的标签
        repo.git.tag("-a", tag_name, "-m", f"Tag created by {user} on {date_str}")
        typer.echo(f"🏷️ Created tag: {tag_name}")

        # 推送标签到远程
        try:
            origin.push(tag_name)
            typer.echo(f"📤 Pushed tag {tag_name} to remote")
        except git.GitCommandError as e:
            typer.echo(f"⚠️ Failed to push tag to remote: {e}")
            typer.echo("💡 You can manually push with: git push origin " + tag_name)

        typer.echo("✅ Tag creation completed")
        return True

    except git.GitCommandError as e:
        typer.echo(f"❌ Error creating tag: {e}")
        return False
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")
        return False

    typer.echo("🏷️ Tag END")


@app.command()
def squash(
    msg: Annotated[str, typer.Option(prompt="🤖 Input Squash Message")] = "squash",
    need_push: bool = True,
):
    typer.echo("🧹 Squash START")
    typer.echo("🧹 Squash: Your base is {base}")
    repo.git.reset(base)
    commit(msg)
    if need_push:
        force_push()
    typer.echo("🧹 Squash END")


# @app.command()
def reset(push: bool = True) -> bool:
    global base

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
            return False
        typer.echo("🪓 Reset END")
        return True
    return False


# @app.command()
def rebase(need_push: bool = True) -> bool:
    global base

    master_mr = find_latest_master_mr()
    if master_mr.committed_datetime > base.committed_datetime:
        typer.echo("🌳 Rebase START")

        if is_conflict():
            if typer.confirm(
                "💥 Conflict: You need to resolve manually, then force-push, continue?"
            ):
                if my_commits_num() > 1:
                    if typer.confirm(
                        "💥 Conflict: Squash may reduce conflict, continue?"
                    ):
                        squash("conflicts", False)
                    else:
                        typer.echo(
                            "💥 Conflict: You might resolve conflict multiple times"
                        )
            else:
                typer.echo("🌳 Rebase STOP")
                return False
        typer.echo("🌳 Rebase: Latest Master Merge-Request is {master_mr}")
        repo.git.rebase(master_mr, autostash=True)
        base = master_mr

        if need_push:
            force_push()

        typer.echo("🌳 Rebase END")
        return True
    return False


@app.command()
def auto():
    typer.echo("🤖 Auto Small-Git...")
    sync()
    need_push = False
    need_push |= reset(False)
    need_push |= rebase(False)
    if need_push:
        force_push()
    submod()
    os.system("uv sync")
    typer.echo("✅ DONE")


if __name__ == "__main__":
    app()
