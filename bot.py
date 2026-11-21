"""Submission entry point. Standard library only; stdout belongs to the game."""
import mechfight
from sentinel.strategy import Bot

if __name__ == "__main__":
    mechfight.run(Bot)
