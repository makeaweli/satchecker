#image for updating TLEs
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /usr/src/app

COPY . .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt
#
