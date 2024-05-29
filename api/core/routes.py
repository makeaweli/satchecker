#!/usr/bin/python3
from datetime import timezone

import requests
from astropy.time import Time
from flask import abort, jsonify, redirect, request
from sqlalchemy.exc import DataError

from core import app, limiter
from core.database.satellite_access import (
    get_ids_for_satelltite_name,
    get_names_for_satellite_id,
    get_tles,
)
from core.database.tle_access import (
    get_tle,
    parse_tle,
    propagate_and_create_json_results,
)
from core.utils import (
    extract_parameters,
    get_forwarded_address,
    jd_arange,
    validate_parameters,
)

from . import error_messages


# Error handling
@app.errorhandler(404)
def page_not_found(e):
    return (
        "Error 404: Page not found<br /> \
        Check your spelling to ensure you are accessing the correct endpoint.",
        404,
    )


@app.errorhandler(400)
def missing_parameter(e):
    return (
        f"Error 400: Incorrect parameters or too many results to return \
        (maximum of 1000 in a single request)<br /> \
        Check your request and try again.<br /><br />{str(e)}",
        400,
    )


@app.errorhandler(429)
def ratelimit_handler(e):
    return "Error 429: You have exceeded your rate limit:<br />" + e.description, 429


@app.errorhandler(500)
def internal_server_error(e):
    return "Error 500: Internal server error:<br />" + e.description, 500


# Redirects user to the Center for the Protection of Dark and Quiet Sky homepage
@app.route("/")
@app.route("/index")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def root():
    return redirect("https://satchecker.readthedocs.io/en/latest/")


@app.route("/health")
@limiter.exempt
def health():
    try:
        response = requests.get("https://cps.iau.org/tools/satchecker/api/", timeout=10)
        response.raise_for_status()
    except Exception:
        abort(503, "Error: Unable to connect to IAU CPS URL")
    else:
        return {"message": "Healthy"}


@app.route("/ephemeris/name/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_name():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for the given satellite's Two Line Element Data Set at a specified
    Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE
    epoch is necessary.

    Parameters
    ----------
    name: 'str'
        CelesTrak name of object
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    julian_date: 'float'
        UT1 Universal Time Julian Date. An input of 0 will use the TLE epoch.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees
    data_source: 'str'
        Original source of TLE data (celestrak or spacetrack)

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """
    parameters = extract_parameters(
        request,
        [
            "name",
            "latitude",
            "longitude",
            "elevation",
            "julian_date",
            "min_altitude",
            "max_altitude",
            "data_source",
        ],
    )

    parameters = validate_parameters(
        parameters, ["name", "latitude", "longitude", "elevation", "julian_date"]
    )

    # Test JD format
    try:
        jd = Time(parameters["julian_date"], format="jd", scale="ut1")
    except Exception:
        abort(500, error_messages.INVALID_JD)

    tle = get_tle(
        parameters["name"], False, parameters["data_source"], jd.to_datetime()
    )
    return propagate_and_create_json_results(
        parameters["location"],
        [jd],
        tle[0].tle_line1,
        tle[0].tle_line2,
        tle[0].date_collected,
        parameters["name"],
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle[1].sat_number,
        parameters["data_source"],
    )


@app.route("/ephemeris/name-jdstep/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_name_jdstep():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for the given satellite's name with the Two Line Element Data Set at
    a specified Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE epoch
    is necessary.

    Parameters
    ----------
    name: 'str'
        CelesTrak name of object
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    startjd: 'float'
        UT1 Universal Time Julian Date to start ephmeris calculation.
    stopjd: 'float'
        UT1 Universal Time Julian Date to stop ephmeris calculation.
    stepjd: 'float'
        UT1 Universal Time Julian Date timestep.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees
    data_source: 'str'
        Original source of TLE data (celestrak or spacetrack)

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """

    parameters = extract_parameters(
        request,
        [
            "name",
            "latitude",
            "longitude",
            "elevation",
            "startjd",
            "stopjd",
            "stepjd",
            "min_altitude",
            "max_altitude",
            "data_source",
        ],
    )

    parameters = validate_parameters(
        parameters, ["name", "latitude", "longitude", "elevation", "startjd", "stopjd"]
    )

    jd0 = float(parameters["startjd"])
    jd1 = float(parameters["stopjd"])

    # default to 2 min
    jds = 0.00138889 if parameters["stepjd"] is None else float(parameters["stepjd"])

    jd = jd_arange(jd0, jd1, jds)

    if len(jd) > 1000:
        abort(400)

    tle = get_tle(
        parameters["name"], False, parameters["data_source"], jd[0].to_datetime()
    )
    return propagate_and_create_json_results(
        parameters["location"],
        jd,
        tle[0].tle_line1,
        tle[0].tle_line2,
        tle[0].date_collected,
        parameters["name"],
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle[1].sat_number,
        parameters["data_source"],
    )


@app.route("/ephemeris/catalog-number/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_catalog_number():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for the given satellite's catalog number using the Two Line Element
    Data Set at the specified Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE epoch
    is necessary.

    Parameters
    ----------
    catalog: 'str'
        Satellite Catalog Number of object
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    julian_date: 'float'
        UT1 Universal Time Julian Date. An input of 0 will use the TLE epoch.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees
    data_source: 'str'
        Original source of TLE data (celestrak or spacetrack)

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """
    parameters = extract_parameters(
        request,
        [
            "catalog",
            "latitude",
            "longitude",
            "elevation",
            "julian_date",
            "min_altitude",
            "max_altitude",
            "data_source",
        ],
    )

    parameters = validate_parameters(
        parameters, ["catalog", "latitude", "longitude", "elevation", "julian_date"]
    )

    # Converting string to list
    try:
        jd = Time(parameters["julian_date"], format="jd", scale="ut1")
    except Exception:
        abort(500, error_messages.INVALID_JD)

    tle = get_tle(
        parameters["catalog"], True, parameters["data_source"], jd.to_datetime()
    )

    return propagate_and_create_json_results(
        parameters["location"],
        [jd],
        tle[0].tle_line1,
        tle[0].tle_line2,
        tle[0].date_collected,
        tle[1].sat_name,
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle[1].sat_number,
        parameters["data_source"],
    )


@app.route("/ephemeris/catalog-number-jdstep/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_catalog_number_jdstep():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for the given satellite's catalog number with the Two Line Element Data
    Set at the specfied Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE epoch
    is necessary.

    Parameters
    ----------
    catalog: 'str'
        Satellite catalog number of object (NORAD ID)
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    startjd: 'float'
        UT1 Universal Time Julian Date to start ephmeris calculation.
    stopjd: 'float'
        UT1 Universal Time Julian Date to stop ephmeris calculation.
    stepjd: 'float'
        UT1 Universal Time Julian Date timestep.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees
    data_source: 'str'
        Original source of TLE data (celestrak or spacetrack)

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """
    parameters = extract_parameters(
        request,
        [
            "catalog",
            "latitude",
            "longitude",
            "elevation",
            "startjd",
            "stopjd",
            "stepjd",
            "min_altitude",
            "max_altitude",
            "data_source",
        ],
    )

    parameters = validate_parameters(
        parameters,
        ["catalog", "latitude", "longitude", "elevation", "startjd", "stopjd"],
    )

    jd0 = float(parameters["startjd"])
    jd1 = float(parameters["stopjd"])

    # default to 2 min
    jds = 0.00138889 if parameters["stepjd"] is None else float(parameters["stepjd"])

    jd = jd_arange(jd0, jd1, jds)

    if len(jd) > 1000:
        app.logger.info("Too many results requested")
        abort(400)

    tle = get_tle(
        parameters["catalog"], True, parameters["data_source"], jd[0].to_datetime()
    )
    return propagate_and_create_json_results(
        parameters["location"],
        jd,
        tle[0].tle_line1,
        tle[0].tle_line2,
        tle[0].date_collected,
        tle[1].sat_name,
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle[1].sat_number,
        parameters["data_source"],
    )


@app.route("/ephemeris/tle/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_tle():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for a given Two Line Element Data Set at the specified Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE epoch
    is necessary.

    Parameters
    ----------
    tle: 'str'
        Two line element set of object
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    julian_date: 'float'
        UT1 Universal Time Julian Date. An input of 0 will use the TLE epoch.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """

    parameters = extract_parameters(
        request,
        [
            "tle",
            "latitude",
            "longitude",
            "elevation",
            "julian_date",
            "min_altitude",
            "max_altitude",
        ],
    )

    parameters = validate_parameters(
        parameters, ["tle", "latitude", "longitude", "elevation", "julian_date"]
    )

    # Converting string to list
    try:
        jd = Time(parameters["julian_date"], format="jd", scale="ut1")
    except Exception:
        abort(500, error_messages.INVALID_JD)

    tle = parse_tle(parameters["tle"])
    return propagate_and_create_json_results(
        parameters["location"],
        [jd],
        tle.tle_line1,
        tle.tle_line2,
        tle.date_collected,
        tle.name,
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle.catalog,
        "user",
    )


@app.route("/ephemeris/tle-jdstep/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_ephemeris_by_tle_jdstep():
    """Returns satellite location and velocity information relative to the observer's
    coordinates for the given satellite's catalog number using the Two Line Element
    Data Set at a specified Julian Date.

    **Please note, for the most accurate results, a Julian Date close to the TLE epoch
    is necessary.

    Parameters
    ----------
    tle: 'str'
        Two line element set of object
    latitude: 'float'
        The observers latitude coordinate (positive value represents north,
        negative value represents south)
    longitude: 'float'
        The observers longitude coordinate (positive value represents east,
        negative value represents west)
    elevation: 'float'
        Elevation in meters
    startjd: 'float'
        UT1 Universal Time Julian Date to start ephmeris calculation.
    stopjd: 'float'
        UT1 Universal Time Julian Date to stop ephmeris calculation.
    stepjd: 'float'
        UT1 Universal Time Julian Date timestep.
    min_altitude: 'float'
        Minimum satellite altitude in degrees
    max_altitude: 'float'
        Maximum satellite altitude in degrees

    Returns
    -------
    response: 'dictionary'
        JSON output with satellite information - see json_output() for format
    """
    parameters = extract_parameters(
        request,
        [
            "tle",
            "latitude",
            "longitude",
            "elevation",
            "startjd",
            "stopjd",
            "stepjd",
            "min_altitude",
            "max_altitude",
        ],
    )

    parameters = validate_parameters(
        parameters, ["tle", "latitude", "longitude", "elevation", "startjd", "stopjd"]
    )

    jd0 = float(parameters["startjd"])
    jd1 = float(parameters["stopjd"])

    # default to 2 min
    jds = 0.00138889 if parameters["stepjd"] is None else float(parameters["stepjd"])

    jd = jd_arange(jd0, jd1, jds)

    if len(jd) > 1000:
        app.logger.info("Too many results requested")
        abort(400)

    tle = parse_tle(parameters["tle"])
    return propagate_and_create_json_results(
        parameters["location"],
        jd,
        tle.tle_line1,
        tle.tle_line2,
        tle.date_collected,
        tle.name,
        parameters["min_altitude"],
        parameters["max_altitude"],
        tle.catalog,
        "user",
    )


@app.route("/tools/norad-ids-from-name/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_norad_ids_from_name():
    """
    Returns the NORAD ID(s) for a given satellite name.

    Parameters
    ----------
    name: 'str'
        The name of the satellite.

    Returns
    -------
    response: 'list'
        A list of NORAD IDs associated with the given satellite name.
    """
    satellite_name = request.args.get("name").upper()

    if satellite_name is None:
        abort(400)

    try:
        norad_ids_and_dates = get_ids_for_satelltite_name(satellite_name)

        # Extract the IDs from the result set
        norad_ids_and_dates = [
            {
                "name": satellite_name,
                "norad_id": id_date[0],
                "date_added": id_date[1].strftime("%Y-%m-%d %H:%M:%S %Z"),
            }
            for id_date in norad_ids_and_dates
        ]

        return jsonify(norad_ids_and_dates)
    except Exception as e:
        app.logger.error(e)
        return None


@app.route("/tools/names-from-norad-id/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_names_from_norad_id():
    """
    Retrieves any satellite names associated with a NORAD ID.

    This function queries the database for satellites that match the provided NORAD ID,
    which is retrieved from the request arguments. The names of the matching satellites
    are then returned in a JSON format.

    If an error occurs during the process, the error is logged and None is returned.

    Returns:
        list: A list of satellite names in JSON format, or None if an error occurs.
    """
    satellite_id = request.args.get("id")
    if satellite_id is None:
        abort(400)

    try:
        satellite_names_and_dates = get_names_for_satellite_id(satellite_id)

        # Extract the names from the result set
        names_and_dates = [
            {
                "name": name_date[0],
                "norad_id": satellite_id,
                "date_added": name_date[1].strftime("%Y-%m-%d %H:%M:%S %Z"),
            }
            for name_date in satellite_names_and_dates
        ]

        for name, date_added in satellite_names_and_dates:
            # Convert date_added to UTC before printing it
            date_added_utc = date_added.astimezone(timezone.utc)
            print(name, date_added_utc)

        return jsonify(names_and_dates)
    except Exception as e:
        app.logger.error(e)
        return None


@app.route("/tools/get-tle-data/")
@limiter.limit(
    "100 per second, 2000 per minute", key_func=lambda: get_forwarded_address(request)
)
def get_tle_data():
    satellite_id = request.args.get("id")
    id_type = request.args.get("id_type")
    start_date = request.args.get("start_date_jd")
    end_date = request.args.get("end_date_jd")

    if satellite_id is None:
        abort(400)

    if id_type != "catalog" and id_type != "name":
        abort(400)

    start_date = (
        Time(start_date, format="jd", scale="ut1")
        .to_datetime()
        .replace(tzinfo=timezone.utc)
        if start_date
        else None
    )
    end_date = (
        Time(end_date, format="jd", scale="ut1")
        .to_datetime()
        .replace(tzinfo=timezone.utc)
        if end_date
        else None
    )

    try:
        tle_data = get_tles(satellite_id, id_type, start_date, end_date)

        # Extract the TLE data from the result set
        tle_data = [
            {
                "satellite_name": tle.tle_satellite.sat_name,
                "satellite_id": tle.tle_satellite.sat_number,
                "tle_line1": tle.tle_line1,
                "tle_line2": tle.tle_line2,
                "epoch": tle.epoch.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "date_collected": tle.date_collected.strftime("%Y-%m-%d %H:%M:%S %Z"),
            }
            for tle in tle_data
        ]

        return jsonify(tle_data)

    except Exception as e:
        if isinstance(e, DataError):
            abort(500, error_messages.NO_TLE_FOUND)
        app.logger.error(e)
        return None
