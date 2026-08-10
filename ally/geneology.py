"""
Geneology of personalities stretching back x generations.
Each person in the geneology has a personality that is a mix of their two parent's personalities,
derived via Gemini. Root ancestors are assigned unique random base personalities from PERSONALITIES.
"""

import random
from typing import List, Tuple, Optional
from pydantic import BaseModel

from ally.personalities import PERSONALITIES
from llm.gemini_provider import GeminiProvider


class PersonalityFusion(BaseModel):
    name: str
    personality: str


class Person:
    def __init__(
        self,
        name: str,
        personality: str,
        parents: Optional[Tuple["Person", "Person"]] = None,
        generation: int = 0,
    ):
        self.name: str = name
        self.personality: str = personality
        self.parents: Optional[Tuple["Person", "Person"]] = parents
        self.generation: int = generation

    def __repr__(self) -> str:
        return f"Person(name={self.name!r}, generation={self.generation}, personality={self.personality[:40]}...)"


GENEOLOGY_PROMPT = (
    "You are an expert in narrative design and personality synthesis for AI companions. "
    "You are given the personalities of two parent entities. Your task is to breed them "
    "into a cohesive, compelling new child persona.\n\n"
    "Parent 1:\n{parent1}\n\n"
    "Parent 2:\n{parent2}\n\n"
    "Guidelines for the merge:\n"
    "1. CORE IDENTITY: Select one dominant vibe/archetype from one parent as the structural foundation, "
    "and weave specific behavioral quirks, vocabulary, or philosophies from the other parent into it naturally.\n"
    "2. AVOID LAUNDRY LISTS: Do not just stitch sentences together. Find the thematic intersection between "
    "the parents (e.g., how would a min-maxer view a cosmic horror entity? How does a speedrunner handle being a blank slate?).\n"
    "3. COHERENT VOICE: Keep the description focused, punchy, and evocative. "
    "It must be written strictly in the second person ('You are...').\n\n"
    "Provide your response in the following format:\n"
    "Name: [A creative synthesized name]\n"
    "Personality: [The synthesized second-person description]"
)


class Geneology:
    def __init__(
        self,
        provider: GeminiProvider,
        generations: int = 3,
        model: str = "gemini-3.5-flash",
    ):
        self.provider = provider
        self.generations = generations
        self.model = model
        self.root: Optional[Person] = None
        self._all_members: List[Person] = []

    def build(self) -> Person:
        """Build the geneology tree going back `generations` generations."""
        self._all_members = []
        base_personalities = list(PERSONALITIES.items())

        # Number of root ancestors at depth `generations` is 2^generations
        num_roots = 2 ** self.generations
        if num_roots > len(base_personalities):
            raise ValueError(
                f"Requested {self.generations} generations requires {num_roots} root ancestors (2^{self.generations}), "
                f"but only {len(base_personalities)} unique base personalities are available in PERSONALITIES "
                f"(maximum supported without replacement is 3 generations yielding 8 root ancestors)."
            )

        # Select unique random base personalities for the root ancestors
        selected_bases = random.sample(base_personalities, num_roots)

        # Build recursively from generation `generations` down to 0
        self.root = self._build_subtree(self.generations, selected_bases)
        return self.root

    def _build_subtree(
        self, current_gen: int, available_bases: List[Tuple[str, str]]
    ) -> Person:
        if current_gen == 0:
            # Leaf node (root ancestor)
            name, personality = available_bases.pop(0)
            person = Person(
                name=name,
                personality=personality,
                parents=None,
                generation=self.generations,
            )
            self._all_members.append(person)
            return person
        else:
            # Internal node: has two parents from previous generation level
            half = len(available_bases) // 2
            parent1 = self._build_subtree(current_gen - 1, available_bases[:half])
            parent2 = self._build_subtree(current_gen - 1, available_bases[half:])

            # Mix personalities using Gemini
            prompt = GENEOLOGY_PROMPT.format(
                parent1=parent1.personality, parent2=parent2.personality
            )
            result = self.provider.generate_structured(
                model=self.model,
                contents=[prompt],
                schema=PersonalityFusion,
            )

            person = Person(
                name=result.name,
                personality=result.personality,
                parents=(parent1, parent2),
                generation=self.generations - current_gen,
            )
            self._all_members.append(person)
            return person

    def get_all_personalities(self) -> List[str]:
        """Return a list of all personality descriptions of everyone in the family tree."""
        return [member.personality for member in self._all_members]

    def get_all_members(self) -> List[Person]:
        """Return a list of all Person objects in the family tree."""
        return self._all_members


if __name__ == "__main__":
    generations = 2
    provider = GeminiProvider()
    # 3 generations back (2^3 = 8 root ancestors, fitting within the 10 base personalities)
    geneology = Geneology(provider=provider, generations=generations)
    print(f"Building geneology tree ({generations} generations)...")
    descendant = geneology.build()
    print(f"\nFinal Descendant: {descendant.name} (Gen {descendant.generation})")
    print(f"Personality:\n{descendant.personality}")
    
    print(f"\nTotal family members in tree: {len(geneology.get_all_members())}")
    print("\nAll family tree personalities:")
    for i, p in enumerate(geneology.get_all_personalities()):
        print(f"\n--- Member {i} ---")
        print(p)
