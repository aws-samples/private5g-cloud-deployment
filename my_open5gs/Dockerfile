# Use the official Ubuntu 22.04 image as the base
FROM ubuntu:22.04

# Set environment variables if needed
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ARG DEBIAN_FRONTEND=noninteractive

# Install necessary packages
RUN apt-get update && \
    apt-get install -y gnupg curl python3-pip python3-setuptools python3-wheel ninja-build build-essential flex bison git cmake libsctp-dev libgnutls28-dev libgcrypt-dev libssl-dev libidn11-dev libmongoc-dev libbson-dev libyaml-dev libnghttp2-dev libmicrohttpd-dev libcurl4-gnutls-dev libnghttp2-dev libtins-dev libtalloc-dev meson && \
    curl -fsSL https://pgp.mongodb.com/server-6.0.asc | gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg --dearmor && \
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-6.0.list && \
    apt-get update && \
    apt-get install -y mongodb-org && \
    apt-get clean && \
    apt-get install -y net-tools && \
    apt-get install -y iproute2 && \
    apt-get install -y iptables && \
    apt-get install -y vim && \
    rm -rf /var/lib/apt/lists/*

# Copy the open5gs repository from your local machine to the image
COPY open5gs /open5gs

# Clone the open5gs repository and build
RUN cd open5gs && \
    meson build --prefix=`pwd`/install && \
    ninja -C build && \
    cd build && \
    ninja install && \
    cp /open5gs/install/bin/open5gs* /usr/bin/

# Expose MongoDB default port and any other ports your application might use
EXPOSE 27017

# Keep the container running (this is a simple way to prevent it from exiting)
CMD ["tail", "-f", "/dev/null"]

