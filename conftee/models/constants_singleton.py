from ..utils.constants import WORD_TYPE_REGEXES, SUBNET_CLUSTERS


def determine_cluster(word: str):
    """
    Description:
        Helper function to universally handle conditions of how a word's cluster should be determined.
    """
    word_lower = word.lower()

    is_subnet_member_of = False
    for cluster_pre in SUBNET_CLUSTERS:
        if word_lower.find(cluster_pre) == 0:
            is_subnet_member_of = cluster_pre
            break

    if is_subnet_member_of:
        # If any of those cluster prefixes is present, return it
        return is_subnet_member_of

    # Other cases, also return the substring before the first underscore, or the whole word if splitting fails
    return word_lower.split("_", 1)[0]


def print_const_var_clusters():
    clusters = {}
    for word in ConstantsSingleton.get_const_var_names():
        cluster = ConstantsSingleton.get_instance().find(determine_cluster(word))
        if cluster not in clusters:
            clusters[cluster] = []
        clusters[cluster].append(word)

    for cluster, words in clusters.items():
        print("Cluster:", cluster)
        print("Words:", words)
        print()


class DisjointSet:
    def __init__(self):
        """
        Description: A simple disjoint set class currently only used for WORD_TYPE_REGEXES key clustering in ConstantsSingleton.
        If there comes a need to use it elsewhere, move it into a seperate file.
        """
        self.parent = {}

    def make_set(self, x):
        self.parent[x] = x

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x != root_y:
            self.parent[root_y] = root_x


class ConstantsSingleton:
    """
    Description: A Singleton currently only used for holding a DisjointSet built from WORD_TYPE_REGEXES's keys.
    It only has one instance when alive, as any Singleton should.
    """

    _instance = None
    # Another class variable to hold the words
    _const_var_names = WORD_TYPE_REGEXES.keys()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls._build_words_disjoint_set()
        return cls._instance

    @classmethod
    def get_const_var_names(cls):
        """
        Description: Class method to get class variable holding all key names in WORD_TYPE_REGEXES.
        """
        return cls._const_var_names

    @classmethod
    def get_clusters_dict(cls):
        """
        Description: Class method to build a dict using the class's DisjointSet.
        """
        clusters_dict = {}
        for word in cls._const_var_names:
            cluster = ConstantsSingleton.get_instance().find(determine_cluster(word))
            if cluster not in clusters_dict:
                clusters_dict[cluster] = []
            clusters_dict[cluster].append(word)

        return clusters_dict

    @staticmethod
    def _build_words_disjoint_set():
        disjoint_set = DisjointSet()
        words = ConstantsSingleton._const_var_names
        for word in words:
            prefix = determine_cluster(word)
            disjoint_set.make_set(prefix)
            disjoint_set.make_set(word)

        for word in words:
            prefix = determine_cluster(word)
            disjoint_set.union(prefix, word)

        return disjoint_set
