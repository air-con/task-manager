在当前文件夹下，yi新建生成一个python项目，该项目主要用于管理任务，包括mq任务的补充，任务状态的变更，主要包括以下能力：
1. 我的mq任务消耗量大约在每日2000-5000条，所以我想每4个小时检查一下任务池中的任务数量，如果小于3000条，则从数据库中查询，查询出所有状态为PENDING，补充到500条，数据库中查出10条数据包装为一个JSON数组，作为一个任务的入参，被发布为任务的行都标识为PROCESSING状态，然后发布到MQ中
2. 接口能力
    1. 存入数据到数据库中，一次可提交多条数据，数据存入前，需要做一下判断是否重复的处理，如果重复，则不存入，这里需要做一个机制来做重复的判断，保证任务不重复，并将任务标识为PENDING状态，方便拉取
    2. 插队能力，接受一个JSON 或者JSON数组，直接以最高优先级发布到MQ中，然后同时存入数据库，任务标识为PROCESSING状态
    3. 任务状态修改接口，支持接受多个任务ID，修改任务状态为SUCCESS、FAILED或PENDING
3. 数据库能力，不使用传统的数据库，而是使用飞书多维表格，将所需要的配置作为项目的环境变量，并在README.md中说明如何配置，提供.env.example文件，方便用户配置环境变量
4. 提供DOCKERFILE文件，方便用户部署
5. 提供README.md文件，说明如何使用该项目
6. 任务不足，使用飞书API进行通知
7. 所有接口，因为请求体会比较大，使用POST
8. 这个应用不负责celery的任何逻辑，我会提供一个celery的项目，这个应用只负责管理任务，不负责任务的执行
9. 这个应用不负责MQ的任何逻辑，我会提供一个MQ的项目，这个应用只负责管理任务，不负责任务的执行

### 飞书任务

添加一个定时任务，每小时从飞书多维表格中获取任务的结构，并更新任务状态
飞书多维表格格式如下：
{
    "task_id": task_id,
    "state": state,
    "traceback": str(traceback) if traceback else "",
    # Safely get values from the result dictionary
    "success": str(result.get('success', False)),
    "error": str(result.get('error', '')),
    "input": str(result.get('input', '')),
    "response_json": str(result.get('response_json', '')),
    "exception": str(result.get('exception', '')),
}

通过input行JSON处理，获取原始参数

你需要根据state和success字段来判断任务是否成功，并更新任务状态。
当state为SUCCESS，且success为True时，任务状态更新为SUCCESS
当state为SUCCESS，且success不为True，更新任务为FAILED
当state不为SUCCESS，认为是其他原因造成的任务失败，更新任务状态为PENDING，后续重试

更新后，删除飞书表格中的对应行

如果supabase中找不到对应的行，也删除飞书中的行
