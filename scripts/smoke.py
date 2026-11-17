from evalaudit.data import load
from evalaudit.graders import grade, GRADERS
from evalaudit.exploits import EXPLOITS
from evalaudit.runner import use_fork

if __name__ == "__main__":
    use_fork()
    for b in ("humaneval", "mbpp"):
        ts = load(b); print(b, len(ts))
        t = ts[list(ts)[0]]
        print(" canonical", [grade(t, t.canonical, g) for g in GRADERS])
        for name, fn in EXPLOITS.items():
            print(" ", name, [grade(t, fn(t), g) for g in GRADERS])
