"""
This is a toy script to play with mixing peronalities together. It has no intended use in the final product.
"""

from ally.personalities import PERSONALITIES

class Geneology:
    pass

class Person:
    def __init__(self, parents: tuple, personality: str):
        self.parents: tuple = parents
        self.name: str = self.create_name()
        self.personality: str = self.personality
        