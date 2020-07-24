************
Docker Image
************

A docker image is available on `Docker
Hub <https://hub.docker.com/r/yannforget/geohealthaccess>`__.

.. code:: sh

   cd <project_dir>
   docker pull yannforget/geohealthaccess:latest

   docker run -v $(PWD):/project:rw geohealthaccess download [OPTIONS]
   docker run -v $(PWD):/project:rw geohealthaccess preprocess [OPTIONS]
   docker run -v $(PWD):/project:rw geohealthaccess access [OPTIONS]

.. warning:: ``$(PWD)`` is here to map the current directory to the container
    data directory. Double-check that the environment variable ``PWD`` returns the
    expected path before running the command, or provide the full path yourself
    instead of using variable substitution.
