"""
 Copyright (c) 2018 Intel Corporation

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

from collections import deque
from re import match, compile

import logging as log
import networkx as nx

from mo.graph.graph import Node
from mo.utils.error import Error
from mo.utils.utils import refer_to_faq_msg


def backward_bfs_for_operation(start_node: Node, op_names: list):
    """
    Find node with 'op' attribute equal to one of from 'op_name', searching in the backward direction.
    In case of branching algorithm goes into each branch, but if it can't find layer in one of them it returns
    empty list.

    :param start_node: Start node for BFS algorithm
    :param op_names: The list with names of operations to search
    """
    ret = []
    q = deque([start_node])
    while len(q) != 0:
        node = q.popleft()
        in_nodes_size = len(node.in_nodes())
        for id in range(in_nodes_size):  # in_nodes() can return either list or dict
            pnode = node.in_node(id)
            if pnode.kind == 'op':
                if pnode.has_valid('op') and pnode.op in op_names:
                    if pnode.id not in ret:
                        ret.append(pnode.id)
                else:
                    q.append(pnode)
            elif pnode.kind == 'data' and pnode.value is None:
                q.append(pnode)
    return [Node(start_node.graph, x) for x in ret]


def bfs_search(graph: nx.MultiDiGraph, start_nodes: list = list()):
    """
    Performs breadth-first search over a graph and returns a list of nodes in the BFS order.
    :param graph: networkx graph to traverse.
    :param start_nodes: list of start nodes of the graph. If the list is empty then start from all nodes that do not
    have input nodes.
    :return: the list of nodes in the BFS order.
    """
    result = list()
    if len(start_nodes) == 0:
        start_nodes = [node_name for node_name in graph.nodes() if len(graph.in_edges(node_name)) == 0]

    visited = set(start_nodes)
    d = deque(start_nodes)

    while len(d) != 0:
        cur_node_name = d.popleft()
        result.append(cur_node_name)
        for src_node, dst_node in graph.out_edges(cur_node_name):
            if dst_node not in visited:
                d.append(dst_node)
                visited.add(dst_node)
    return result


def dfs(graph: nx.MultiDiGraph, node_name: str, visited: set):
    """
    Implementation of the depth-first search algorithm starting from the specific node.
    :param graph: networkx graph to operate on.
    :param node_name: node name to start search from.
    :param visited: set of already visited nodes.
    :return: list of nodes in the DFS-visit order.
    """
    order = []
    stack = [node_name]
    while len(stack) != 0:
        node_name = stack[0]
        stack.pop(0)
        visited.add(node_name)
        has_child = False
        for _, out_node_name in graph.out_edges(node_name):
            if out_node_name not in visited:
                stack.insert(0, node_name)
                stack.insert(0, out_node_name)
                has_child = True
                break
        if not has_child:
            order.append(node_name)
    return order


def pseudo_topological_sort(graph: nx.MultiDiGraph, reverse: bool = False):
    """
    The function performs topological sort but doesn't check for cycle existence. So it may produce wrong nodes order
    for some applications.
    :param graph: graph to pseudo-topologically sort.
    :param reverse: flag indicating whether need to reverse nodes order.
    :return: nodes in the topological sort if cycle doesn't exist and in pseudo-topological sort if not.
    """
    nodes_without_inputs = list()
    for node_name in graph.nodes():
        if len(graph.in_edges(node_name)) == 0:
            nodes_without_inputs.append(node_name)
    order = list()
    visited = set()
    for node_name in nodes_without_inputs:
        if node_name not in visited:
            order.extend(dfs(graph, node_name, visited))

    if reverse:
        return order
    else:
        return list(reversed(order))


def nodes_matching_name_pattern(graph: nx.MultiDiGraph, pattern: str):
    """
    Returns list of node names of the graph that match regular expression.
    :param graph: graph to operate on.
    :param pattern: regular expression describing node name pattern.
    :return: list of matched node names.
    """
    compiled_pattern = compile(pattern)
    return [node_name for node_name in list(graph.nodes()) if match(compiled_pattern, node_name)]


def is_connected_component(graph: nx.MultiDiGraph, node_names: list):
    """
    Checks that specified list of nodes forms a connected sub-graph. It ignores edges direction.
    The algorithm is the following. Run BFS from one of the nodes from the node_names list ignoring edges order and
    visiting only nodes from the node_names list. Prepare list of visited nodes. If this list is equal to the
    node_names list (we actually check that the node_names set is sub-set of 'visited' set that is equivalent) then the
    sub-graph is connected.
    :param graph: graph to operate on.
    :param node_names: list of node names to be checked.
    :return: Result of the check.
    """
    if len(node_names) == 0:
        return True

    d = deque([node_names[0]])
    visited = set([node_names[0]])
    while len(d) != 0:
        cur_node_name = d.popleft()
        visited.add(cur_node_name)
        # find adjacent nodes from the list of node_names. Ignoring edges direction
        adj_nodes = [src_node for src_node, _ in graph.in_edges(cur_node_name) if src_node in node_names] + \
                    [dst_node for _, dst_node in graph.out_edges(cur_node_name) if dst_node in node_names]
        for adj_node in adj_nodes:
            if adj_node not in visited:
                d.append(adj_node)
                visited.add(adj_node)
    return set(node_names).issubset(visited)


def sub_graph_between_nodes(graph: nx.MultiDiGraph, start_nodes: list, end_nodes: list):
    """
    Finds nodes of the sub-graph between 'start_nodes' and 'end_nodes'. Input nodes for the sub-graph nodes are also
    added to the sub-graph. Constant inputs of the 'start_nodes' are also added to the sub-graph.
    :param graph: graph to operate on.
    :param start_nodes: list of nodes names that specifies start nodes.
    :param end_nodes: list of nodes names that specifies end nodes.
    :return: list of nodes of the identified sub-graph or None if the sub-graph cannot be extracted.
    """
    sub_graph_nodes = list()
    visited = set(start_nodes)
    d = deque(start_nodes)

    nx.set_node_attributes(graph, name='prev', values=None)
    while len(d) != 0:
        cur_node_name = d.popleft()
        sub_graph_nodes.append(cur_node_name)
        if cur_node_name not in end_nodes:  # do not add output nodes of the end_nodes
            for _, dst_node_name in graph.out_edges(cur_node_name):
                if dst_node_name not in visited:
                    d.append(dst_node_name)
                    visited.add(dst_node_name)
                    graph.node[dst_node_name]['prev'] = cur_node_name

        for src_node_name, _ in graph.in_edges(cur_node_name):
            # add input nodes for the non-start_nodes
            if cur_node_name not in start_nodes and src_node_name not in visited:
                d.append(src_node_name)
                graph.node[src_node_name]['prev'] = cur_node_name
                visited.add(src_node_name)

    # use forward dfs to check that all end nodes are reachable from at least one of input nodes
    forward_visited = set()
    for start_node in start_nodes:
        dfs(graph, start_node, forward_visited)
    for end_node in end_nodes:
        if end_node not in forward_visited:
            raise Error('End node "{}" is not reachable from start nodes: {}. '.format(end_node, start_nodes) +
                        refer_to_faq_msg(74))

    for node_name in sub_graph_nodes:
        # sub-graph should not contain Placeholder nodes
        if graph.node[node_name].get('op', '') == 'Placeholder':
            path = list()
            cur_node = node_name
            while cur_node and 'prev' in graph.node[cur_node]:
                path.append(str(cur_node))
                cur_node = graph.node[cur_node]['prev']
            log.debug("The path from input node is the following: {}".format('\n'.join(path)))
            raise Error('Sub-graph contains network input node "{}". '.format(node_name) +
                        refer_to_faq_msg(75))
    return sub_graph_nodes


def node_neighbourhood(node_name: str, depth: int, next_node_fn):
    """
    Find neighbourhood of the node..
    :param node_name: name of the node to find neighbourhood for.
    :param depth: maximum depth of search nodes.
    :param next_node_fn: callable that accepts node name and should return list of adjacent nodes.
    :return: list of names of nodes in the neighbourhood.
    """
    dist = dict()
    dist[node_name] = 0
    deq = deque([node_name])
    while len(deq) != 0:
        cur_node_name = deq.popleft()
        cur_dist = dist[cur_node_name]
        if cur_dist < depth:
            for next_node_name in next_node_fn(cur_node_name):
                next_dist = dist.setdefault(next_node_name, depth + 1)
                if next_dist > cur_dist + 1:
                    dist[next_node_name] = cur_dist + 1
                    deq.append(next_node_name)
    return list(dist.keys())


def node_incoming_neighbourhood(graph: nx.MultiDiGraph, node_name: str, depth: int):
    """
    Find input neighbourhood of the node.
    :param graph: graph to operate on.
    :param node_name: name of the node to find neighbourhood for.
    :param depth: maximum depth of input nodes.
    :return: list of names of nodes in the neighbourhood.
    """
    return node_neighbourhood(node_name, depth, lambda node_name: [u for u, v in graph.in_edges([node_name])])


def node_outcoming_neighbourhood(graph: nx.MultiDiGraph, node_name: str, depth: int):
    """
    Find output neighbourhood of the node.
    :param graph: graph to operate on.
    :param node_name: name of the node to find neighbourhood for.
    :param depth: maximum depth of output nodes.
    :return: list of names of nodes in the neighbourhood.
    """
    return node_neighbourhood(node_name, depth, lambda node_name: [v for u, v in graph.out_edges([node_name])])


def scope_output_nodes(graph: nx.MultiDiGraph, scope: str, scope_delimiter: str='/'):
    """
    The function returns nodes producing output of the sub-graph defined by scope (name prefix). The node is considered
    output of the scope if it is in this scope and it's output is outside of the scope.
    :param graph: graph to operate on.
    :param scope: string with scope (prefix of the node name).
    :param scope_delimiter: delimiter between scope parts.
    :return: list of Node objects which are outputs of the scope.
    """
    if scope[-1] != scope_delimiter:
        scope += scope_delimiter

    result = set()
    for node_id in graph.nodes():
        if node_id.startswith(scope):
            for _, out_node_name in graph.out_edges(node_id):
                if not out_node_name.startswith(scope):
                    result.add(node_id)
                    break
    return [Node(graph, node_id) for node_id in result]
