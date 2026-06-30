#!/bin/bash

usage() {
  echo "Usage: $0 -c COMPONENT -u DOCKER_USER -p DOCKER_PASSWORD -t TAG" 1>&2
}

# Get the options
while getopts ":h:c:u:p:t:" option; do
   case ${option} in
      h)
         usage
         exit;;
      c)
         COMPONENT=${OPTARG};;
      u)
         DOCKER_USER=${OPTARG};;
      p)
         DOCKER_PASSWORD=${OPTARG};;
      t)
         TAG=${OPTARG};;

     \?)
         echo "Error: Invalid option"
         exit;;
   esac
done

echo "Access the Container Registry"
echo "$DOCKER_PASSWORD" | docker login ghcr.io -u $DOCKER_USER --password-stdin

build_push_one_component() {
    COMPONENT=$1
    DOCKER_NAMESPACE="ghcr.io/$DOCKER_USER"

    echo "Start building the $COMPONENT image"
    if [[ $COMPONENT == "bcc-python" ]]
    then
    docker build -t $DOCKER_NAMESPACE/casmella-$COMPONENT:$TAG tools/$COMPONENT/
    else
    docker build -t $DOCKER_NAMESPACE/casmella-$COMPONENT:$TAG -f docker/$COMPONENT/Dockerfile .
    fi

    #echo "Start pushing the $COMPONENT image"
    #docker push $DOCKER_NAMESPACE/casmella-$COMPONENT:$TAG
}

if [[ $COMPONENT == "all" ]]
then
    build_push_one_component controller
    build_push_one_component agent
    build_push_one_component sdg
else
    build_push_one_component $COMPONENT
fi
