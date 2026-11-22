# Tests of the rules in rules.yml. A comment that starts with the word ruleid marks a line that must match.
# ruleid: optimal-discretizer-no-kwargs-bag
def bag(**options):
    return options


# ok: optimal-discretizer-no-kwargs-bag
def named(a, *, b=1):
    return a, b


def chain(x):
    # ruleid: optimal-discretizer-no-elif-chain-on-one-value
    if x == 1:
        return "a"
    elif x == 2:
        return "b"
    elif x == 3:
        return "c"
    return "d"


def two_cases(x):
    # ok: optimal-discretizer-no-elif-chain-on-one-value
    if x == 1:
        return "a"
    elif x == 2:
        return "b"
    return "c"


class Base:
    def method(self):
        # ruleid: optimal-discretizer-no-not-implemented-stub
        raise NotImplementedError


def reads(path):
    # ruleid: optimal-discretizer-domain-does-no-io
    return path.read_text()


def shows(x):
    # ruleid: optimal-discretizer-domain-does-no-io
    print(x)


# ruleid: optimal-discretizer-no-manual-beartype
@beartype
def decorated(x):
    return x


def bare_error(x):
    if x < 0:
        # ruleid: optimal-discretizer-no-bare-value-error
        raise ValueError("negative")
    if x > 9:
        # ruleid: optimal-discretizer-no-bare-value-error
        raise ValueError("large") from None
    # ruleid: optimal-discretizer-no-bare-value-error
    raise ValueError


def own_error(x):
    if x < 0:
        # ok: optimal-discretizer-no-bare-value-error
        raise EmptyInputError("negative")
    try:
        return int(x)
    except ValueError:
        # ok: optimal-discretizer-no-bare-value-error
        raise


# ruleid: optimal-discretizer-return-attrs-not-container
def returns_dict(x) -> dict[str, float]:
    return {"a": x}


# ruleid: optimal-discretizer-return-attrs-not-container
def returns_tuple(x) -> tuple[str, float]:
    return ("a", x)


# ruleid: optimal-discretizer-return-attrs-not-container
def returns_list_of_tuples(x) -> list[tuple[float, str]]:
    return [(x, "a")]


# ruleid: optimal-discretizer-return-attrs-not-container
def returns_list_of_dicts(x) -> list[dict[str, float]]:
    return [{"a": x}]


# ok: optimal-discretizer-return-attrs-not-container
def returns_attrs(x) -> Fields:
    return Fields(x)


# ok: optimal-discretizer-return-attrs-not-container
def returns_homogeneous_tuple(x) -> tuple[float, ...]:
    return (x,)


# ok: optimal-discretizer-return-attrs-not-container
def returns_list(x) -> list[float]:
    return [x]


# ok: optimal-discretizer-return-attrs-not-container
def returns_suppressed(x) -> dict[str, float]:  # nosemgrep: optimal-discretizer-return-attrs-not-container -- test of the opt-out
    return {"a": x}


def now():
    # ruleid: optimal-discretizer-no-naive-now
    naive = datetime.now()
    # ruleid: optimal-discretizer-no-naive-now
    utc = datetime.datetime.utcnow()
    # ok: optimal-discretizer-no-naive-now
    instant = whenever.Instant.now()
    return naive, utc, instant


def accepts(frame):
    # ruleid: optimal-discretizer-no-frame-type-branches, optimal-discretizer-polymorphism-not-type-branches
    if isinstance(frame, pl.DataFrame):
        return "polars"
    # ruleid: optimal-discretizer-no-frame-type-branches
    if isinstance(frame, pandas.DataFrame):
        return "pandas"
    # ok: optimal-discretizer-no-frame-type-branches
    return narwhals.from_native(frame).columns


def poll(client):
    # ruleid: optimal-discretizer-no-sleep-loop
    while True:
        if client.ready():
            return
        time.sleep(1)


async def poll_async(client):
    # ruleid: optimal-discretizer-no-sleep-loop
    while True:
        if await client.ready():
            return
        await anyio.sleep(1)


def consume(queue):
    # ok: optimal-discretizer-no-sleep-loop
    while True:
        item = queue.get()
        if item is None:
            return
        handle(item)


async def fan_out(a, b):
    # ruleid: optimal-discretizer-structured-concurrency
    await asyncio.gather(a(), b())
    # ruleid: optimal-discretizer-structured-concurrency
    asyncio.create_task(a())
    # ok: optimal-discretizer-structured-concurrency
    async with anyio.create_task_group() as group:
        group.start_soon(a)


def load_model(path, types):
    # ruleid: optimal-discretizer-skops-load-trusted-true
    first = skops.io.load(path, trusted=True)
    # ruleid: optimal-discretizer-skops-load-trusted-true
    second = sio.load(path, trusted=True)
    # ok: optimal-discretizer-skops-load-trusted-true
    third = sio.load(path, trusted=types)
    return first, second, third


# ruleid: optimal-discretizer-asdict-recurse-false
copy_nested = Fields(**attrs.asdict(fields))

# ok: optimal-discretizer-asdict-recurse-false
copy_flat = Fields(**attrs.asdict(fields, recurse=False))


# ruleid: optimal-discretizer-no-object-type
def takes_object(value: object) -> str:
    return str(value)


# ruleid: optimal-discretizer-no-object-type
def returns_object(value: str) -> object:
    return value


# ruleid: optimal-discretizer-no-object-type
def takes_nested_object(values: Mapping[str, list[object]]) -> int:
    return len(values)


# ruleid: optimal-discretizer-no-object-type
def takes_object_union(value: str | object = "a") -> str:
    return str(value)


class Holder:
    # ruleid: optimal-discretizer-no-object-type
    labels: tuple[object, ...]


# ruleid: optimal-discretizer-no-object-type
type Loose = list[object]


# ruleid: optimal-discretizer-no-object-type
def takes_object_args(*values: object) -> int:
    return len(values)


# ruleid: optimal-discretizer-no-object-type, optimal-discretizer-no-kwargs-bag
def takes_object_kwargs(**values: object) -> int:
    return len(values)


# ruleid: optimal-discretizer-no-object-type
def takes_string_object(values: "list[object]") -> int:
    return len(values)


# ok: optimal-discretizer-no-object-type
def takes_string_named(values: "list[objects]") -> int:
    return len(values)


def takes_object_in_a_long_signature(
    first: str,
    # ruleid: optimal-discretizer-no-object-type
    second: object,
) -> str:
    return first


def suppresses_in_a_long_signature(
    first: str,
    # ok: optimal-discretizer-no-object-type
    second: object,  # nosemgrep: optimal-discretizer-no-object-type -- test of the opt-out on the line of the hint
) -> str:
    return first


# ok: optimal-discretizer-no-object-type
def takes_named(value: str | float | None) -> str:
    return str(value)


# ok: optimal-discretizer-no-object-type
def calls_object() -> object_count:
    return isinstance(1, object)


# ok: optimal-discretizer-no-object-type
def takes_suppressed(value: object) -> str:  # nosemgrep: optimal-discretizer-no-object-type -- test of the opt-out
    return str(value)


def checks_concrete(value, other):
    # ruleid: optimal-discretizer-isinstance-abstract-type
    a = isinstance(value, dict)
    # ruleid: optimal-discretizer-isinstance-abstract-type
    b = isinstance(value, (str, list))
    # ruleid: optimal-discretizer-isinstance-abstract-type
    c = isinstance(value, str | frozenset)
    # ruleid: optimal-discretizer-isinstance-abstract-type
    d = issubclass(type(value), set)
    # ruleid: optimal-discretizer-isinstance-abstract-type
    e = type(other) is dict
    # ruleid: optimal-discretizer-isinstance-abstract-type
    f = type(other) in (list, tuple)
    # ruleid: optimal-discretizer-isinstance-abstract-type
    g = other.__class__ is set
    # ruleid: optimal-discretizer-isinstance-abstract-type
    h = type(other).__name__ == "dict"
    # ruleid: optimal-discretizer-isinstance-abstract-type
    i = other.__class__.__name__ in ("list", "str")
    # ruleid: optimal-discretizer-isinstance-abstract-type
    j = is_bearable(value, dict[str, int])
    # ruleid: optimal-discretizer-isinstance-abstract-type
    k = beartype.door.die_if_unbearable(value, list[str])
    return a, b, c, d, e, f, g, h, i, j, k


def checks_abstract(value, other):
    # ok: optimal-discretizer-isinstance-abstract-type
    a = isinstance(value, Mapping)
    # ok: optimal-discretizer-isinstance-abstract-type
    b = isinstance(value, (str, collections.abc.Set))
    # ok: optimal-discretizer-isinstance-abstract-type
    c = isinstance(value, OrderedDict | tuple)
    # ok: optimal-discretizer-isinstance-abstract-type
    d = isinstance(other, typing.Sequence)
    # ok: optimal-discretizer-isinstance-abstract-type
    e = type(other).__name__ == "dictionary"
    # ok: optimal-discretizer-isinstance-abstract-type
    f = is_bearable(value, Mapping[str, int])
    return a, b, c, d, e, f


def matches_concrete(value):
    match value:
        # ruleid: optimal-discretizer-isinstance-abstract-type, optimal-discretizer-polymorphism-not-type-branches
        case dict():
            return 1
        # ruleid: optimal-discretizer-isinstance-abstract-type
        case str() | list():
            return 2
    return 0


def matches_abstract(value):
    match value:
        # ok: optimal-discretizer-isinstance-abstract-type
        case {"a": a}:
            return a
        # ok: optimal-discretizer-isinstance-abstract-type
        case [first, *_]:
            return first
        # ok: optimal-discretizer-isinstance-abstract-type
        case str(text) if text in list(KNOWN):
            return text
    return 0


def branches_with_elif(shape):
    # ruleid: optimal-discretizer-polymorphism-not-type-branches
    if isinstance(shape, Circle):
        return shape.radius
    elif isinstance(shape, Square):
        return shape.side
    return 0


def branches_with_returns(shape):
    # ruleid: optimal-discretizer-polymorphism-not-type-branches
    if isinstance(shape, Circle):
        return shape.radius
    size = 0
    if isinstance(shape, Square):
        size = shape.side
    return size


def branches_on_type_is(shape):
    # ruleid: optimal-discretizer-polymorphism-not-type-branches
    if type(shape) is Circle:
        return shape.radius
    elif shape.__class__ == Square:
        return shape.side
    return 0


def branches_on_names(shape):
    # ruleid: optimal-discretizer-polymorphism-not-type-branches
    if type(shape).__name__ == "Circle":
        return shape.radius
    if type(shape) in (Square, Rectangle):
        return shape.side
    return 0


def branches_on_attributes(shape):
    # ruleid: optimal-discretizer-polymorphism-not-type-branches
    if hasattr(shape, "radius") and shape.radius:
        return shape.radius
    elif hasattr(shape, "side"):
        return shape.side
    return 0


def branches_on_two_values(left, right):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    if type(left) is Circle:
        return left.radius
    if hasattr(right, "side"):
        return right.side
    return 0


def branches_with_match(shape):
    match shape:
        # ruleid: optimal-discretizer-polymorphism-not-type-branches
        case Circle():
            return shape.radius
        case Square(side=side):
            return side
    return 0


def narrows_a_record(value):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    if isinstance(value, str):  # nosemgrep: optimal-discretizer-polymorphism-not-type-branches -- test of the opt-out
        return value
    elif isinstance(value, float):
        return str(value)
    return ""


def tells(shape):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    return shape.size()


def narrows_once(selected):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    if isinstance(selected, str):
        raise InvalidOptionError(selected)
    return list(selected)


def narrows_two_values(left, right):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    if isinstance(left, str):
        return left
    if isinstance(right, str):
        return right
    return ""


def matches_values(kind):
    # ok: optimal-discretizer-polymorphism-not-type-branches
    match kind:
        case "a":
            return 1
        case "b":
            return 2
    return 0
