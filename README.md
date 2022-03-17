# aws-iam-find-unused-credentials-org
A sample Lambda function that finds IAM Users in all of the AWS Accounts in your AWS Organization that have not logged into the console ever, or in the last x days.

This code may be useful if you are not using AWS Config (the preferred option) and use IAM Users rather than identity federation/SSO (also the preferred option).

This code is a sample and should not be used in a Production Environment. Please evaluate and test in a safe environment.

# To Use
1. Deploy a stackset that creates a role in all of your AWS Organization accounts that your Lambda function execution role will assume. The role must have the following permissions:
  - "iam:ListUsers"
  - "iam:GetUser"
  - "sts:AssumeRole"
    - "Resource": "arn:aws:iam::[AccountID where Lambda function is deployed]:role/[lambda-execution-role]"

2. Create a Lambda function. You can create this in any account in your Organization. Create it with the following settings:
  - Runtime = Python 3.9
  - Architecture = arm64

3. Modify the Lambda execution role permissions to allow:
  - "logs:CreateLogGroup"
  - "logs:CreateLogStream"
  - "logs:PutLogEvents"
  - "organizations:ListAccounts"
  - "sts:AssumeRole"
    - "Resource": "arn:aws:iam::*:role/[role-to-be-assumed]

4. Upload the "lambda_function.zip" file to the Lambda function you have created. This will create 2 files inside the function: lambda_function.py and aws_partitions.py

5. Update lambda_function.py with the following:
  - Line 36: replace the ou_id with your own OrgId
  - Line 120: Replace the "5" with the number of days you deem enough to mark a role as no longer used
  - Line 186: replace the iam_assumed_role_name with the assumed role you created in step 1

6. Deploy the function

7. Create a Test Event using the default "Hello World" template. You can leave everything as default.

8. Run Test and view the resulting log files. You should see the list of AWS Accounts being evaluated, the number of user accounts being evaluated in each account and, once all accounts have been evaluated, a list of user accounts and their respective AWS Accounts that have either never been logged into or that have not been logged into in the number of days specified in step 5

9. When you're ready, complete the code by having the payload "action queue" on line 175 sent somewhere useful. The code as-is just prints the contents to the log file.
