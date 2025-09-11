from dataclasses import dataclass

import git
import typer

app = typer.Typer()

user = git.Actor.name
assert user is not None
email = git.Actor.email


repo = git.Repo(".")
origin = repo.remotes["origin"]
origin.fetch(prune=True, tags=True, prune_tags=True)

master = origin.refs["master"]
my = repo.active_branch


@dataclass
class SmallTeamGit:
    def __post_init__(self):
        assert email is not None

        temp = repo.merge_base(my, master)
        assert len(temp) == 1
        self.base= temp[0]

        self.latest_mr = next(repo.iter_commits(master, max_count=1))
        self.laster_my_mr = None
        for commit in repo.iter_commits(master):
            if commit.author.email and email.lower() in commit.author.email.lower():
                self.laster_my_mr = commit
                break

    @app.command()
    def hello(self):
        print("Hello World")

    @app.command()
    def rebase(self):
        if (
            self.laster_my_mr
            and self.laster_my_mr.committed_datetime > self.base.committed_datetime
        ):
            repo.git.reset(self.laster_my_mr.hexsha)
            self.base = self.laster_my_mr

        if self.latest_mr.committed_datetime > self.base.committed_datetime:
            repo.git.reset(self.base)
            repo.git.add(A=True)
            repo.commit("auto update")
            repo.git.rebase(self.latest_mr.hexsha, autostash=True)
            if not repo.index.unmerged_blobs():
                origin.push(force_with_leave=True)
            else:
                print("you need to resolve merge conflict")

    @app.command()
    def create(self, postfix: str = ""):
        pass

    @app.command()
    def sync(self):
        origin.pull(rebase=True, autostash=True)
        origin.push()


if __name__ == "__main__":
    app()
    s = SmallTeamGit()
