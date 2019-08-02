#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Wrapper script for CloudFormation provisioning

The following CI/CD environment variables need to be set:
    - `AWS_KEY`             > The AWS AccessKey
    - `AWS_KEYID`           > The AWS KeyId
    - `AWS_REGION`          > The AWS Region.
    - `BILLING_ENV`         > The identifier for billing.
    - `STACK_NAME`          > The name of the Stack.
    - `TEAM`                > The name of the Development Team.

codeauthor: 'gn0mish@protonmail.com'
version: 1.0

TODO:
    - Write custom botocore waiter for Stack creation.
    - Improve the way provision() results in create_stack()
'''

# import python libs
import os
import sys
import time

# import 3rd party libs
import boto3
import botocore

# Set debug/logging level for Gitlab CI/CD
DEBUG = True
if DEBUG:
    import pprint

# Import the Cloud Formation template
TEMPLATE = open('./aws/cloudformation/cloudformation.template', 'r').read()

# Setting Gitlab CI/CD variables to python globals.
AWS_KEY = os.environ['AWS_KEY']
AWS_KEYID = os.environ['AWS_KEYID']
AWS_REGION = os.environ['AWS_REGION']
BILLING_ENV = os.environ['BILLING_ENV']
STACK_NAME = os.environ['STACK_NAME']
TEAM = os.environ['TEAM']

# pylint struggles with long lines, so we disable it here.
# pylint: disable=C0301


def _get_conn(service='cloudformation'):
    '''
    Generates a boto3 client for the given service.

    :param str service: The service to generate resource for.
                        Defaults to AWS CloudFormation.

    Inherits Gitlab CI/CD environment variables:
        - `AWS_KEYID`
        - `AWS_KEY`
        - `AWS_REGION`
    '''
    if DEBUG:
        print('[debug]  Created conn:service:client.')
    return boto3.client(
        service,
        aws_access_key_id=AWS_KEYID,
        aws_secret_access_key=AWS_KEY,
        region_name=AWS_REGION,
    )


def _get_conn2(service='cloudformation'):
    '''
    Generates a boto3 resource for the given service.

    :param str service: The service to generate resource for.
                        Defaults to AWS CloudFormation.

    Inherits Gitlab CI/CD environment variables:
        - `AWS_KEYID`
        - `AWS_KEY`
        - `AWS_REGION`
    '''
    if DEBUG:
        print('[debug]  Created conn2:resource:client.')
    return boto3.resource(
        service,
        aws_access_key_id=AWS_KEYID,
        aws_secret_access_key=AWS_KEY,
        region_name=AWS_REGION,
    )


def validate_template(template):
    '''
    Validate the given template file, before excecuting the create or update
    functions..
    '''
    ret = False
    try:
        conn = _get_conn()
        print('\t  Validating template.')
        conn.validate_template(TemplateBody=template)
        print('\t✓ Template validated.')
        ret = True
    except botocore.exceptions.ClientError as err:
        print('[ERROR]  Malformed or invalid template or properties.')
        sys.exit(err)
    return ret


def provision(template):
    '''
    Checks if the AWS CloudFormation stack allready exists or not, then run an
    update or create function.
    
    Inherits Gitlab CI/CD environment variables:
        - `STACK_NAME`
    '''
    ret = False
    try:
        conn = _get_conn()
        if DEBUG:
            print('[debug]  Checking stacks')
        validated = validate_template(template)
        if validated:
            check = conn.describe_stacks(StackName=STACK_NAME)
            if DEBUG:
                pprint.pprint(check['Stacks'])
            for stack in check['Stacks']:
                if STACK_NAME in stack['StackName']:
                    update_stack(template)
    # describe_stacks doesn't return a value, just an error if it doesn't
    # exists, so we catch it here.
    except botocore.exceptions.ClientError as err:
        if str(err).endswith('does not exist'):
            create_stack(template)
            ret = True
        else:
            sys.exit(err)
    return ret


def wait_for_stack(stack_name, wait_time):
    '''
    A filthy waiter.
    '''
    ret = False
    if DEBUG:
        print('[debug]  Waiting: {} seconds'.format(wait_time))
    conn = _get_conn()
    wait_list = [
        'CREATE_IN_PROGRESS',
        'DELETE_COMPLETE_CLEANUP_IN_PROGRESS',
        'DELETE_IN_PROGRESS',
        'UPDATE_IN_PROGRESS',
        'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
        'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
        'ROLLBACK_COMPLETE',
        'ROLLBACK_IN_PROGRESS',
    ]
    while conn.describe_stacks(StackName=stack_name)['Stacks'][0]['StackStatus'] in wait_list: 
        if DEBUG:
            reason = conn.describe_stacks(StackName=stack_name)['Stacks'][0]['StackStatus']
            print('[debug]  Waiting for state "{}" to be resolved.'.format(reason))
        time.sleep(wait_time)
    ret = True
    return ret


def set_tags(stack_name, tag_value, team):
    '''
    Set's or updates the Top-Level Tags on the Stack.
    This function needs boto3.resource instead of boto3.client.

    Inherits Gitlab CI/CD environment variables:
        - `BILLING_ENV`
        - `STACK_NAME`
    '''
    ret = False
    try:
        print('\t  Setting Stack-level tags.')
        wait_for_stack(stack_name, 10)
        conn = _get_conn2()
        conn.Stack(stack_name).update(
            Capabilities=['CAPABILITY_IAM'],
            UsePreviousTemplate=True,
            Tags=[
                {'Key': 'Billing_Env', 'Value': tag_value},
                {'Key': 'Team', 'Value': team},
                {'Key': 'Project', 'Value': stack_name},
                ]
        )
        wait_for_stack(stack_name, 10)
        print('\t✓ Tags set.')
        ret = True
    except botocore.exceptions.ClientError as err:
        if str(err).endswith('to be performed.'):
            print('\t✓ No tag updates to be performed.')
        else:
            sys.exit(err)
    return ret


def update_stack(template):
    '''
    Updates an AWS CloudFormation stack.

    Inherits Gitlab CI/CD environment variables:
        - `STACK_NAME`
    '''
    ret = False
    try:
        conn = _get_conn()
        print('\t  Checking update for CloudFormation stack "{}"'.format(STACK_NAME))
        wait_for_stack(STACK_NAME, 10)
        conn.update_stack(
            StackName=STACK_NAME,
            Capabilities=['CAPABILITY_IAM'],
            TemplateBody=template
        )
        wait_for_stack(STACK_NAME, 10)
        print('\t✓ Updated CloudFormation stack "{}".'.format(STACK_NAME))
        set_tags(STACK_NAME, BILLING_ENV, TEAM)
        ret = True
    except botocore.exceptions.ClientError as err:
        if DEBUG:
            pprint.pprint(err)
        print('\t✓ No updates found in the template file.')
        set_tags(STACK_NAME, BILLING_ENV, TEAM)
        ret = True
    return ret


def create_stack(template):
    '''
    Creates an AWS CloudFormation stack.

    Inherits Gitlab CI/CD environment variables:
        - `STACK_NAME`
    '''
    ret = False
    try:
        conn = _get_conn()
        print('\t  Creating stack {}'.format(STACK_NAME))
        build = conn.create_stack(
            StackName=STACK_NAME,
            Capabilities=['CAPABILITY_IAM'],
            TemplateBody=template,
            OnFailure='DO_NOTHING',
        )
        if DEBUG:
            print('[debug]  StackId:'.format(build['StackId']))
        wait_for_stack(STACK_NAME, 60)
        print('\t✓ Created CloudFormation stack for {}.'.format(STACK_NAME))
        set_tags(STACK_NAME, BILLING_ENV, TEAM)
        ret = True
    except botocore.exceptions.ClientError as err:
        sys.exit(err)
    return ret


if __name__ == '__main__':
    print('[ CloudFormation Provisioning ]')
    provision(TEMPLATE)
