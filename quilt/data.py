"""
Magic module that maps its submodules to Quilt tables.

Submodules have the following format: quilt.data.$user.$package.$table

E.g.:
  import quilt.data.$user.$package as $package
  print $package.$table
or
  from quilt.data.$user.$package import $table
  print $table

The corresponding data is looked up in `quilt_modules/$user/$package.h5`
in ancestors of the current directory.
"""

import imp
import os.path
import sys

from six import iteritems

from .tools.core import GroupNode as CoreGroupNode
from .tools.store import PackageStore

__path__ = []  # Required for submodules to work

class PackageNode(object):
    """
    Abstract class that represents a group or a leaf node in a package.
    """
    def __init__(self, package, prefix, node):
        # Can't instantiate it directly
        assert self.__class__ != PackageNode.__class__

        self._package = package
        self._prefix = prefix
        self._node = node

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._package == other._package and self._prefix == other._prefix
        return NotImplemented

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self._package, self._prefix))

    def __repr__(self):
        finfo = self._package.get_path()[:-len(PackageStore.PACKAGE_FILE_EXT)]
        pinfo = self._prefix
        return "<%s %r:%r>" % (self.__class__.__name__, finfo, pinfo)


class GroupNode(PackageNode):
    """
    Represents a group in a package. Allows accessing child objects using the dot notation.
    """
    def __init__(self, package, prefix, node):
        super(GroupNode, self).__init__(package, prefix, node)

        for name, child_node in iteritems(node.children):
            assert not name.startswith('_')
            child_prefix = prefix + '/' + name
            if isinstance(child_node, CoreGroupNode):
                child = GroupNode(package, child_prefix, child_node)
            else:
                child = DataNode(package, child_prefix, child_node)
            setattr(self, name, child)

    def __repr__(self):
        pinfo = super(GroupNode, self).__repr__()
        kinfo = '\n'.join(self._keys())
        return "%s\n%s" % (pinfo, kinfo)

    def _data_keys(self):
        """
        every child key referencing a dataframe
        """
        return [name for name, node in iteritems(self._node.children)
                if not isinstance(node, CoreGroupNode)]

    def _group_keys(self):
        """
        every child key referencing a group that is not a dataframe
        """
        return [name for name, node in iteritems(self._node.children)
                if isinstance(node, CoreGroupNode)]

    def _keys(self):
        """
        keys directly accessible on this object via getattr or .
        """
        return list(self._node.children)


class DataNode(PackageNode):
    """
    Represents a dataframe or a file. Allows accessing the contents using `()`.
    """
    def __call__(self):
        return self.data()

    def data(self):
        """
        Returns the contents of the node: a dataframe or a file path.
        """
        return self._package.get_obj(self._node)


class FakeLoader(object):
    """
    Fake module loader used to create intermediate user and package modules.
    """
    def __init__(self, path):
        self._path = path

    def load_module(self, fullname):
        """
        Returns an empty module.
        """
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = self._path
        mod.__loader__ = self
        mod.__path__ = []
        mod.__package__ = fullname
        return mod

class PackageLoader(object):
    """
    Module loader for Quilt tables.
    """
    def __init__(self, path, package):
        self._path = path
        self._package = package

    def load_module(self, fullname):
        """
        Returns an object that lazily looks up tables and groups.
        """
        mod = sys.modules.get(fullname)
        if mod is not None:
            return mod

        # We're creating an object rather than a module. It's a hack, but it's approved by Guido:
        # https://mail.python.org/pipermail/python-ideas/2012-May/014969.html

        mod = GroupNode(self._package, '', self._package.get_contents())
        sys.modules[fullname] = mod
        return mod

class ModuleFinder(object):
    """
    Looks up submodules.
    """
    @staticmethod
    def find_module(fullname, path=None):
        """
        Looks up the table based on the module path.
        """
        if not fullname.startswith(__name__ + '.'):
            # Not a quilt submodule.
            return None

        submodule = fullname[len(__name__) + 1:]
        parts = submodule.split('.')

        if len(parts) == 1:
            for store_dir in PackageStore.find_store_dirs():
                # find contents
                file_path = os.path.join(store_dir, parts[0])
                if os.path.isdir(file_path):
                    return FakeLoader(file_path)
        elif len(parts) == 2:
            user, package = parts
            pkgobj = PackageStore.find_package(user, package)
            if pkgobj:
                file_path = pkgobj.get_path()
                return PackageLoader(file_path, pkgobj)

        return None

sys.meta_path.append(ModuleFinder)
