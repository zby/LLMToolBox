import inspect
import json

from pydantic import BaseModel
from docstring_parser import parse
from typing import Any, Dict, Callable,List, Tuple, get_type_hints


class SchemaGenerator:
    def __init__(self, strict=True, name_mappings=None):
        if name_mappings is None:
            name_mappings = []
        self.strict = strict
        self.name_mappings = name_mappings

    def func_name_to_schema(self, func_name):
        for fname, sname in self.name_mappings:
            if func_name == fname:
                return sname
        return func_name

    def schema_name_to_func(self, schema_name):
        for fname, sname in self.name_mappings:
            if schema_name == sname:
                return fname
        return schema_name


    @classmethod
    def _recursive_purge_titles(cls, d: Dict[str, Any]) -> None:
        """Remove a titles from a schema recursively"""
        if isinstance(d, dict):
            for key in list(d.keys()):
                if key == 'title' and "type" in d.keys():
                    del d[key]
                else:
                    cls._recursive_purge_titles(d[key])

    from typing import Callable, Any, Dict

    def function_schema(self, function: Callable) -> Dict[str, Any]:
        description = ''
        parameters = inspect.signature(function).parameters
        if not len(parameters) == 1:
            raise TypeError(f"Function {function.__name__} requires {len(parameters)} parameters but we generate schemas only for one parameter functions")

        # there's exactly one parameter
        name, param = list(parameters.items())[0]
        param_class = param.annotation

        if not issubclass(param_class, BaseModel):
            raise TypeError(f"The only parameter of function {function.__name__} is not a subclass of pydantic BaseModel")

        params_schema = param_class.model_json_schema()
        self._recursive_purge_titles(params_schema)

        if 'description' in params_schema:
            description = params_schema['description']
            params_schema.pop('description')
        if function.__doc__:
            if description and self.strict:
                raise ValueError(f"Both function '{function.__name__}' and the parameter class '{param_class.__name__}' have descriptions")
            else:
                description = parse(function.__doc__).short_description

        schema = {
            "name": self.func_name_to_schema(function.__name__),
            "description": description,
        }
        if len(param_class.__annotations__) > 0:  # if the model is not empty,
            schema["parameters"] = params_schema

        return schema

    def generate_tools(self, *functions: Callable) -> list:
        """
        Generates a tools description array for multiple functions.

        Args:
        *functions: A variable number of functions to introspect.

        Returns:
        A list representing the tools structure for a client.chat.completions.create call.
        """
        tools_array = []
        for function in functions:
            # Check return type
            return_type = get_type_hints(function).get('return')
            if return_type is not None and return_type != str:
                raise ValueError(f"Return type of {function.__name__} is {return_type} and not str")

            function_schema = self.function_schema(function)
            tool_item = {
                "type": "function",
                "function": function_schema,
            }
            tools_array.append(tool_item)
        return tools_array

    def generate_functions(self, *functions: Callable) -> list:
        """
        Generates a functions description array for multiple functions.

        Args:
        *functions: A variable number of functions to introspect.

        Returns:
        A list representing the functions structure for a client.chat.completions.create call.
        """
        functions_array = []
        for function in functions:
            # Check return type
            return_type = get_type_hints(function).get('return')
            if return_type is not None and return_type != str:
                raise ValueError(f"Return type of {function.__name__} is not str")

            functions_array.append(self.function_schema(function))
        return functions_array


class ToolResult:
    def __init__(self, tool_name=None, tool_args=None, observations=None, error=None):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.observations = observations
        self.error = error

class ToolBox:
    def __init__(self, strict=True, name_mappings=None,
                 tool_registry=None, generator=None,
                 tool_schemas=None, tool_sets=None,
                 ):
        self.strict = strict
        if tool_registry is None:
            tool_registry = {}
        self.tool_registry = tool_registry
        if name_mappings is None:
            name_mappings = []
        self.name_mappings = name_mappings
        if tool_schemas is None:
            tool_schemas = []
        self.tool_schemas = tool_schemas
        if tool_sets is None:
            tool_sets = []
        self.tool_sets = tool_sets

        if generator is None:
            generator = SchemaGenerator(strict=self.strict, name_mappings=self.name_mappings)
        self.generator = generator

    @classmethod
    def toolbox_from_object(cls, obj, *args, **kwargs):
        instance = cls(*args, **kwargs)
        instance.register_tools_from_object(obj)
        instance.tool_sets.append(obj)
        return instance

    def register_tools_from_object(self, obj):
        functions = []
        methods = inspect.getmembers(obj, predicate=inspect.ismethod)
        for name, method in methods:
            if name.startswith('_'):
                continue
            self.register_tool(method)
            functions.append(method)
        tools = self.generator.generate_tools(*functions)
        self.tool_schemas.extend(tools)

    def register_tool(self, function):
        parameters = inspect.signature(function).parameters

        if not len(parameters) == 1:
            raise TypeError(f"function {function.__name__} requires {len(parameters)} parameters but we work only with one parameter functions")
        name, param = list(parameters.items())[0]
        param_class = param.annotation

        if not issubclass(param_class, BaseModel):
            raise TypeError(f"the only parameter of function {function.__name__} is not a subclass of pydantic basemodel")

        self.tool_registry[function.__name__] = (function, param_class)


    def schema_name_to_func(self, schema_name):
        for fname, sname in self.name_mappings:
            if schema_name == sname:
                return fname
        return schema_name

    def process(self, function_call):
        tool_args = json.loads(function_call.arguments)
        tool_name = function_call.name
        return self._process_unpacked(tool_name, tool_args)

    def _process_unpacked(self, tool_name, tool_args):
        function_name = self.schema_name_to_func(tool_name)
        if function_name is None:
            return ToolResult(tool_name=tool_name, tool_args=tool_args, error=f"Unknown tool name: {tool_name}")
        function, param_class = self.tool_registry[function_name]
        param = param_class(**tool_args)
        observations = function(param)
        return ToolResult(tool_name=tool_name, tool_args=tool_args, observations=observations)

