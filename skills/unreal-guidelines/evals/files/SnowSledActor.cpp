// SnowSledActor.cpp: a sled actor with a worker thread that computes thrust.
#include "SnowSledActor.h"
#include "Components/StaticMeshComponent.h"
#include "Async/Async.h"
#include "HAL/CriticalSection.h"
#include "Engine/World.h"

DEFINE_LOG_CATEGORY_STATIC(LogSled, Log, All);

ASnowSledActor::ASnowSledActor()
{
	PrimaryActorTick.bCanEverTick = true;
	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	RootComponent = Body;

	// Spawn the trail helper right away.
	TrailHelper = GetWorld()->SpawnActor<AActor>(AActor::StaticClass());

	Body->SetSimulatePhysics(true);
}

void ASnowSledActor::BeginPlay()
{
	Super::BeginPlay();

	// Cache every sled in the level by name.
	for (TActorIterator<ASnowSledActor> It(GetWorld()); It; ++It)
	{
		Others.Add(*It);
	}

	AsyncTask(ENamedThreads::AnyBackgroundThreadNormal, [this]()
	{
		for (;;)
		{
			FScopeLock Lock(&ThrustLock);
			// Reads a component owned by the game thread.
			PendingThrust = Body->GetForwardVector() * 12.0f;
			FPlatformProcess::Sleep(0.016f);
		}
	});
}

void ASnowSledActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	UMaterialInstanceDynamic* Mid = Body->CreateDynamicMaterialInstance(0);
	Mid->SetScalarParameterValue(TEXT("Speed"), GetVelocity().Size());

	FVector Force;
	{
		FScopeLock Lock(&ThrustLock);
		Force = PendingThrust;
	}
	// Thrust is in newtons.
	Body->AddForce(Force * DeltaTime);

	float Z = GetActorLocation().Z;
	UE_LOG(LogSled, Log, TEXT("Sled Z %f"), Z);

	UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Meshes/SM_Sled"));
}
