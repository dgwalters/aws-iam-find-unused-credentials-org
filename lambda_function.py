# (c) 2021 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
# This AWS Content is provided subject to the terms of the AWS Customer
# Agreement available at https://aws.amazon.com/agreement/ or other written
# agreement between Customer and Amazon Web Services, Inc.

"""aws-iam-find-unused-credentials-org

This function dynamically queries you AWS Organization for a list of AWS
Accounts and returns a list of IAM Users that have either never logged in or
haven't logged in during the last x days.
"""

import boto3
import os
import logging
import datetime
import dateutil
from aws_partitions import get_partition_for_region

# setup script logging
log = logging.getLogger()
log.setLevel(logging.INFO)

# AWS Organizations Client
org_client = boto3.client('organizations')

# AWS Lambda Client
lambda_client = boto3.client('lambda')


# main Python Function, parses events sent to lambda
def lambda_handler(event, context):

    # environment Variables
    # Replace with your OrgID
    ou_id = 'o-ab12cdefgh'

    # get AWS account details from AWS Organizations
    if ou_id:
        account_list = list_aws_accounts_for_ou(ou_id)
    else:
        account_list = list_all_aws_accounts()
    # loop through all accounts and trigger the IAM Rotation Lambda
    find_unused_credentials(account_list)


def list_all_aws_accounts():
    """
    Gets the current list of all AWS Accounts from AWS Organizations.

    :return The current dict of all AWS Accounts.
    """
    account_list = []
    try:
        # max limit of 20 users per listing
        # use paginator to iterate through each page
        paginator = org_client.get_paginator('list_accounts')
        page_iterator = paginator.paginate()
        for page in page_iterator:
            for acct in page['Accounts']:
                account_list.append(acct)
    except org_client.exceptions.ClientError as error:
        log.error(f'Error: {error}')

    return account_list


def list_aws_accounts_for_ou(ou_id):
    """
    Gets the current list of AWS Accounts in an OU from AWS Organizations.

    :return The current dict of all AWS Accounts.
    """
    log.info(f"Searching for accounts in OU {ou_id}")
    account_list = []

    # first add accounts directly in the ou
    try:
        # max limit of 20 accounts per listing
        # use paginator to iterate through each page
        lafp_paginator = org_client.get_paginator('list_accounts_for_parent')
        lafp_page_iterator = lafp_paginator.paginate(ParentId=ou_id)
        for page in lafp_page_iterator:
            for acct in page['Accounts']:
                account_list.append(acct)
    except org_client.exceptions.ClientError as error:
        log.error(f'Error: {error}')

    # next add accounts in child ous
    try:
        # max limit of 20 children per listing
        # use paginator to iterate through each page
        lc_paginator = org_client.get_paginator('list_children')
        ou_page_iterator = lc_paginator.paginate(
            ParentId=ou_id,
            ChildType='ORGANIZATIONAL_UNIT'
        )
        for page in ou_page_iterator:
            for child in page['Children']:
                # recurse over child ous and add the accounts they contain
                log.info(f"Adding accounts from child OU {child['Id']}")
                account_list += list_aws_accounts_for_ou(child['Id'])
    except org_client.exceptions.ClientError as error:
        log.error(f'Error: {error}')

    log.info(f"Found {len(account_list)} accounts in OU {ou_id}")

    return account_list


def find_unused_credentials(awsAccountArray):
    """
    Evaluates last password use date.

    """
    action_queue = []

    # Calculate the date x days ago to to determine if an account is now unused
    now = datetime.datetime.now(tz=dateutil.tz.gettz('Europe/London'))
    UnusedSinceDays = dateutil.relativedelta.relativedelta(days=5)
    UnusedSinceDate = now - UnusedSinceDays

    for account in awsAccountArray:
        # skip accounts that are suspended
        if account['Status'] != 'ACTIVE':
            continue
        aws_account_id = account['Id']
        log.info(f'Currently evaluating Account ID: {aws_account_id}')

        account_session = get_account_session(aws_account_id)
        iam_client = account_session.client('iam')

        try:
            # Get all Users in AWS Account
            users = iam_client.list_users()['Users']
            if not users:
                log.info('There are no users in this account.')
            else:
                total_users = len(users)

                log.info(
                    f'Starting user loop. There are {total_users}'
                    f' users to evaluate in this account.')
                log.info('---------------------------')

                # Get when password was last used
                for user in users:
                    try:
                        LastPass = user['PasswordLastUsed']
                    except:
                        LastPass = None

                    # If the account has never been logged into, add to queue
                    if LastPass is None:
                        action_queue.append({
                            'AWS Account': aws_account_id,
                            'User ID': user['UserName'],
                            'Last Login': 'None'
                        })

                    # If the account hasn't been used since the date we
                    # calculated earlier, add it to the list with the last used
                    # datetime
                    elif LastPass <= UnusedSinceDate:
                        action_queue.append({
                            'AWS Account': aws_account_id,
                            'User ID': user['UserName'],
                            'Last Login': LastPass
                        })

        except iam_client.exceptions.ClientError as error:
            log.error(f'Error: {error}')

    # Print the action queue to the logs. You should send this somewhere useful
    print(action_queue)


def get_account_session(aws_account_id):

    # Create an STS client object that represents a live connection to the
    # STS service
    base_sts_client = boto3.client('sts')

    # Add the name of the role created in each of your AWS Accounts for the
    # Lambda function to assume
    iam_assumed_role_name = 'example-role'

    my_session = boto3.session.Session()
    my_region = my_session.region_name
    partition = get_partition_for_region(my_region)

    # Call the assume_role method of the STSConnection object and pass the
    # role ARN and a role session name.
    roleArnString = f"arn:{partition}:iam::{aws_account_id}:" \
                    f"role/{iam_assumed_role_name}"

    try:
        credentials = base_sts_client.assume_role(
            RoleArn=roleArnString,
            RoleSessionName="unused-credentials-function"
        )['Credentials']
    except base_sts_client.exceptions.ClientError as error:
        log.error(
            f'Check that AccountID: [{aws_account_id}] has the correct IAM'
            f' Assume Role deployed to it via the CloudFormation StackSet'
            f' Template. Raw Error: {error}')
        raise

    # From the response that contains the assumed role, get the temporary
    # credentials that can be used to make subsequent API calls
    assumed_session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
    return assumed_session
