from datashape import (
    var,
    Record,
    Option,
    string
)

from odo import (
    discover,
    dshape,
    odo,
    resource,
)
import pandas as pd
from six import StringIO

def do_not_infer_types(ds):
    return var * Record([(name, Option(string)) for name in ds[1].names])

def string_resource_to_json(source, infer_data_types=False, **kwargs):
    io = resource(StringIO(source))
    ds = discover(io)
    if not infer_data_types:
        ds = do_not_infer_dtypes(ds)
