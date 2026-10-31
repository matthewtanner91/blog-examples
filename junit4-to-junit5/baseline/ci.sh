#!/bin/sh
set -eu
# Run exactly this entry point on the CI worker after provisioning the pinned JDK/Maven.
mvn -B -ntp clean verify
